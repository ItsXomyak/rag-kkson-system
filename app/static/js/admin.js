// Admin panel — upload PDFs, list/search/delete documents.
(() => {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const uploadList = document.getElementById('upload-list');
  const docsSearch = document.getElementById('docs-search');
  const docsList = document.getElementById('docs-list');
  const docsCount = document.getElementById('docs-count');
  const toastEl = document.getElementById('toast');
  const themeToggle = document.getElementById('admin-theme-toggle');
  const themeIcon = document.getElementById('admin-theme-icon');

  // ── Theme (shares the 'theme' key with the main app) ─────────────────
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
    if (themeIcon) themeIcon.textContent = t === 'dark' ? '☀' : '☾';
  }
  applyTheme(localStorage.getItem('theme') || 'light');
  themeToggle?.addEventListener('click', () => {
    const current = document.documentElement.dataset.theme || 'light';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  });

  const STAGE_LABEL = {
    parsing:   { label: 'Парсинг',   percent: 15 },
    chunking:  { label: 'Чанкинг',   percent: 35 },
    embedding: { label: 'Эмбеддинг', percent: 70 },
    storing:   { label: 'Запись',    percent: 90 },
    done:      { label: 'Готово',    percent: 100 },
    error:     { label: 'Ошибка',    percent: 100 },
  };

  // ── Toast ──────────────────────────────────────────────────────────────
  let toastTimer = null;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2200);
  }

  // ── Upload flow ────────────────────────────────────────────────────────
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
  });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files?.length) uploadFiles(e.target.files);
    e.target.value = '';  // allow re-selecting the same file
  });

  async function uploadFiles(fileList) {
    const files = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (files.length === 0) {
      toast('Нужны .pdf файлы');
      return;
    }

    // Create placeholder rows immediately
    const rows = new Map();
    for (const f of files) {
      const row = createUploadRow(f.name);
      rows.set(f.name, row);
      uploadList.prepend(row.el);
    }

    const formData = new FormData();
    files.forEach(f => formData.append('files', f));

    let resp;
    try {
      resp = await fetch('/admin/upload', { method: 'POST', body: formData });
    } catch (err) {
      for (const f of files) markRowError(rows.get(f.name), 'сеть недоступна');
      toast('Ошибка сети');
      return;
    }

    if (!resp.ok) {
      const detail = await resp.text();
      for (const f of files) markRowError(rows.get(f.name), 'отклонён сервером');
      toast(`Ошибка: ${resp.status}`);
      console.error(detail);
      return;
    }

    const data = await resp.json();

    // Mark rejected files
    for (const rej of (data.rejected || [])) {
      const r = rows.get(rej.file);
      if (r) markRowError(r, rej.reason);
    }

    // Stream progress
    if (data.job_id) {
      openProgressStream(data.job_id, rows);
    }
  }

  function createUploadRow(name) {
    const el = document.createElement('div');
    el.className = 'upload-row';
    el.innerHTML = `
      <div class="upload-row-top">
        <div class="upload-row-name"></div>
        <div class="upload-row-stage">в очереди</div>
      </div>
      <div class="upload-progress"><div class="upload-progress-fill"></div></div>
      <div class="upload-row-detail"></div>
    `;
    el.querySelector('.upload-row-name').textContent = name;
    return {
      el,
      stage: el.querySelector('.upload-row-stage'),
      fill: el.querySelector('.upload-progress-fill'),
      detail: el.querySelector('.upload-row-detail'),
    };
  }

  function markRowError(row, msg) {
    if (!row) return;
    row.el.classList.add('error');
    row.stage.textContent = 'Ошибка';
    row.fill.style.width = '100%';
    row.detail.textContent = msg || '';
  }

  function openProgressStream(jobId, rows) {
    const src = new EventSource(`/admin/progress/${jobId}`);

    src.onmessage = (e) => {
      let ev;
      try { ev = JSON.parse(e.data); } catch { return; }
      const row = rows.get(ev.file);
      if (!row) return;

      const meta = STAGE_LABEL[ev.stage] || { label: ev.stage, percent: 50 };
      row.stage.textContent = meta.label;
      row.fill.style.width = meta.percent + '%';
      row.detail.textContent = ev.detail || '';

      if (ev.stage === 'done') {
        row.el.classList.add('done');
      } else if (ev.stage === 'error') {
        row.el.classList.add('error');
      }
    };

    src.addEventListener('done', () => {
      src.close();
      toast('Загрузка завершена');
      loadDocs(docsSearch.value);
    });

    src.onerror = () => {
      src.close();
      // Refresh anyway — processing may have finished
      loadDocs(docsSearch.value);
    };
  }

  // ── Documents listing ──────────────────────────────────────────────────
  let docsAbort = null;

  async function loadDocs(q = '') {
    if (docsAbort) docsAbort.abort();
    docsAbort = new AbortController();

    const url = '/admin/documents' + (q ? `?q=${encodeURIComponent(q)}` : '');
    try {
      const resp = await fetch(url, { signal: docsAbort.signal });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const rows = await resp.json();
      renderDocs(rows);
    } catch (err) {
      if (err.name === 'AbortError') return;
      docsList.innerHTML = '<div class="docs-error">Не удалось загрузить список</div>';
      console.error(err);
    }
  }

  function renderDocs(rows) {
    docsCount.textContent = rows.length;
    if (rows.length === 0) {
      docsList.innerHTML = '<div class="docs-empty">Ничего не найдено</div>';
      return;
    }

    docsList.innerHTML = '';
    for (const r of rows) {
      const el = document.createElement('div');
      el.className = 'doc-row';
      el.innerHTML = `
        <span class="doc-row-name"></span>
        <span class="doc-row-count"></span>
        <a class="doc-row-download" target="_blank" rel="noopener">Скачать</a>
        <button class="doc-row-delete" type="button">Удалить</button>
      `;
      el.querySelector('.doc-row-name').textContent = r.source_file;
      el.querySelector('.doc-row-count').textContent = `${r.chunk_count} чанк.`;
      const dl = el.querySelector('.doc-row-download');
      dl.href = `/admin/download/${encodeURIComponent(r.source_file)}`;
      dl.setAttribute('download', r.source_file);
      el.querySelector('.doc-row-delete').addEventListener('click', () => deleteDoc(r.source_file, el));
      docsList.appendChild(el);
    }
  }

  async function deleteDoc(sourceFile, rowEl) {
    if (!confirm(`Удалить "${sourceFile}" и все его фрагменты из базы?`)) return;

    try {
      const resp = await fetch(`/admin/documents/${encodeURIComponent(sourceFile)}`, {
        method: 'DELETE',
      });
      if (!resp.ok) {
        toast(`Ошибка удаления (${resp.status})`);
        return;
      }
      const data = await resp.json();
      rowEl.remove();
      const current = parseInt(docsCount.textContent || '0', 10);
      if (!Number.isNaN(current)) docsCount.textContent = Math.max(0, current - 1);
      toast(`Удалено ${data.deleted} чанков`);
      if (!docsList.querySelector('.doc-row')) {
        docsList.innerHTML = '<div class="docs-empty">Ничего не найдено</div>';
      }
    } catch (err) {
      toast('Ошибка сети');
      console.error(err);
    }
  }

  // ── Debounced search ───────────────────────────────────────────────────
  let searchTimer = null;
  docsSearch.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadDocs(docsSearch.value.trim()), 250);
  });

  // ── Initial load ───────────────────────────────────────────────────────
  loadDocs();
})();

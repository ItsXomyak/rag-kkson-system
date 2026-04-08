/* ═══════════════════════════════════════════════
   KKSON RAG — Frontend Application
   ═══════════════════════════════════════════════ */

(function () {
  'use strict';

  /* ── Constants ── */
  const HISTORY_KEY = 'kkson_history_v2';
  const OLD_HISTORY_KEY = 'kkson_history';
  const LANG_KEY = 'kkson_lang';
  const SIDEBAR_KEY = 'kkson_sidebar';
  const MAX_HISTORY = 100;
  const MAX_ANSWER_STORE = 10000; // chars per answer in storage

  /* ── State ── */
  let rawMarkdown = '';
  let currentController = null;
  let loadingInterval = null;
  let isStreaming = false;
  let activeHistoryId = null;
  let sidebarTab = 'history'; // 'history' | 'saved'
  let exportMenuOpen = false;

  /* ── DOM Refs (lazy) ── */
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  /* ══════════════════════════════
     THEME
     ══════════════════════════════ */

  function getTheme() {
    return localStorage.getItem('theme') || 'light';
  }

  function setTheme(t) {
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
    const icon = $('#theme-icon');
    if (icon) icon.textContent = t === 'dark' ? '☀' : '☾';
  }

  function toggleTheme() {
    setTheme(getTheme() === 'dark' ? 'light' : 'dark');
  }

  /* ══════════════════════════════
     i18n
     ══════════════════════════════ */

  const STRINGS = {
    ru: {
      new_search: 'Новый поиск',
      history: 'История',
      saved: 'Избранное',
      search_history: 'Поиск по истории...',
      clear_all: 'Очистить всё',
      no_history: 'Здесь пока пусто',
      no_saved: 'Нет сохранённых ответов',
      theme: 'Тема',
      lang: 'Язык',
      shortcuts: 'Горячие клавиши',
      search_placeholder: 'Введите исследовательский вопрос...',
      keyword_placeholder: 'Ключевое слово (необязательно)',
      search_btn: 'Найти',
      searching: 'Ищем...',
      loading_text: 'Ищем релевантные источники...',
      generating: 'Генерируем обзор литературы...',
      review: 'Обзор литературы',
      copy: 'Копировать',
      copied: 'Скопировано',
      export: 'Экспорт',
      export_md: 'Скачать .md',
      export_txt: 'Скачать .txt',
      copy_md: 'Копировать Markdown',
      sources: 'Источники',
      page: 'стр.',
      welcome_title: 'KKSON',
      welcome_title_accent: 'RAG',
      welcome_sub: 'Поиск и анализ научных статей из журналов, рекомендованных ККСОН МОН РК',
      articles: 'статей в базе',
      journals: 'журналов',
      languages: 'языка',
      step1_title: 'Спросите',
      step1_desc: 'Введите исследовательский вопрос',
      step2_title: 'Найдём',
      step2_desc: 'Поиск по базе научных статей',
      step3_title: 'Ответим',
      step3_desc: 'AI-обзор с цитированием источников',
      try_examples: 'Попробуйте:',
      example1: 'Генетические мутации при колоректальном раке',
      example2: 'NLP методы для казахского языка',
      example3: 'Цифровизация образования в Казахстане',
      example4: 'Экологические проблемы Аральского моря',
      feedback_label: 'Полезно?',
      followup_label: 'Связанные вопросы:',
      error_connection: 'Ошибка подключения',
      shortcut_submit: 'Отправить поиск',
      shortcut_theme: 'Сменить тему',
      shortcut_focus: 'Фокус на поиск',
      shortcut_new: 'Новый поиск',
      shortcut_sidebar: 'Скрыть/показать боковую панель',
      shortcut_help: 'Горячие клавиши',
      shortcut_esc: 'Закрыть',
    },
    kz: {
      new_search: 'Жаңа іздеу',
      history: 'Тарих',
      saved: 'Сақталған',
      search_history: 'Тарих бойынша іздеу...',
      clear_all: 'Барлығын тазалау',
      no_history: 'Әзірге бос',
      no_saved: 'Сақталған жауаптар жоқ',
      theme: 'Тақырып',
      lang: 'Тіл',
      shortcuts: 'Жылдам пернелер',
      search_placeholder: 'Зерттеу сұрағыңызды енгізіңіз...',
      keyword_placeholder: 'Кілт сөз (міндетті емес)',
      search_btn: 'Іздеу',
      searching: 'Іздеуде...',
      loading_text: 'Сәйкес дереккөздерді іздеуде...',
      generating: 'Әдебиеттерге шолу жасалуда...',
      review: 'Әдебиеттерге шолу',
      copy: 'Көшіру',
      copied: 'Көшірілді',
      export: 'Экспорт',
      export_md: '.md жүктеу',
      export_txt: '.txt жүктеу',
      copy_md: 'Markdown көшіру',
      sources: 'Дереккөздер',
      page: 'б.',
      welcome_title: 'KKSON',
      welcome_title_accent: 'RAG',
      welcome_sub: 'ҚР БҒМ ККСОН ұсынған журналдардағы ғылыми мақалаларды іздеу және талдау',
      articles: 'мақала базада',
      journals: 'журнал',
      languages: 'тіл',
      step1_title: 'Сұраңыз',
      step1_desc: 'Зерттеу сұрағыңызды енгізіңіз',
      step2_title: 'Табамыз',
      step2_desc: 'Ғылыми мақалалар базасынан іздейміз',
      step3_title: 'Жауап береміз',
      step3_desc: 'AI-шолу дереккөздермен',
      try_examples: 'Байқап көріңіз:',
      example1: 'Колоректальды рактағы генетикалық мутациялар',
      example2: 'Қазақ тіліне арналған NLP әдістері',
      example3: 'Қазақстандағы білім беруді цифрландыру',
      example4: 'Арал теңізінің экологиялық мәселелері',
      feedback_label: 'Пайдалы ма?',
      followup_label: 'Байланысты сұрақтар:',
      error_connection: 'Қосылу қатесі',
      shortcut_submit: 'Іздеуді жіберу',
      shortcut_theme: 'Тақырыпты ауыстыру',
      shortcut_focus: 'Іздеуге фокус',
      shortcut_new: 'Жаңа іздеу',
      shortcut_sidebar: 'Бүйір панелін көрсету/жасыру',
      shortcut_help: 'Жылдам пернелер',
      shortcut_esc: 'Жабу',
    },
    en: {
      new_search: 'New Search',
      history: 'History',
      saved: 'Saved',
      search_history: 'Search history...',
      clear_all: 'Clear all',
      no_history: 'Nothing here yet',
      no_saved: 'No saved answers',
      theme: 'Theme',
      lang: 'Lang',
      shortcuts: 'Shortcuts',
      search_placeholder: 'Enter your research question...',
      keyword_placeholder: 'Keyword (optional)',
      search_btn: 'Search',
      searching: 'Searching...',
      loading_text: 'Searching for relevant sources...',
      generating: 'Generating literature review...',
      review: 'Literature Review',
      copy: 'Copy',
      copied: 'Copied',
      export: 'Export',
      export_md: 'Download .md',
      export_txt: 'Download .txt',
      copy_md: 'Copy Markdown',
      sources: 'Sources',
      page: 'p.',
      welcome_title: 'KKSON',
      welcome_title_accent: 'RAG',
      welcome_sub: 'Search and analyze scientific articles from KKSON-recommended journals',
      articles: 'articles in database',
      journals: 'journals',
      languages: 'languages',
      step1_title: 'Ask',
      step1_desc: 'Enter your research question',
      step2_title: 'Find',
      step2_desc: 'Search through scientific articles',
      step3_title: 'Answer',
      step3_desc: 'AI review with source citations',
      try_examples: 'Try:',
      example1: 'Genetic mutations in colorectal cancer',
      example2: 'NLP methods for Kazakh language',
      example3: 'Digitalization of education in Kazakhstan',
      example4: 'Environmental problems of the Aral Sea',
      feedback_label: 'Helpful?',
      followup_label: 'Related questions:',
      error_connection: 'Connection error',
      shortcut_submit: 'Submit search',
      shortcut_theme: 'Toggle theme',
      shortcut_focus: 'Focus search',
      shortcut_new: 'New search',
      shortcut_sidebar: 'Toggle sidebar',
      shortcut_help: 'Keyboard shortcuts',
      shortcut_esc: 'Close',
    },
  };

  function getLang() {
    return localStorage.getItem(LANG_KEY) || 'ru';
  }

  function t(key) {
    const lang = getLang();
    return (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.ru[key] || key;
  }

  function applyI18n() {
    $$('[data-i18n]').forEach((el) => {
      const key = el.dataset.i18n;
      const attr = el.dataset.i18nAttr;
      if (attr === 'placeholder') {
        el.placeholder = t(key);
      } else {
        el.textContent = t(key);
      }
    });
  }

  function setLang(lang) {
    localStorage.setItem(LANG_KEY, lang);
    applyI18n();
    // Update active state
    $$('.lang-option').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.lang === lang);
    });
  }

  /* ══════════════════════════════
     HISTORY
     ══════════════════════════════ */

  function getHistory() {
    try {
      return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    } catch {
      return [];
    }
  }

  function saveHistoryList(h) {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(h));
  }

  function migrateOldHistory() {
    const old = localStorage.getItem(OLD_HISTORY_KEY);
    if (!old) return;
    try {
      const items = JSON.parse(old);
      const existing = getHistory();
      const existingQueries = new Set(existing.map((e) => e.query));
      for (const item of items) {
        if (!existingQueries.has(item.q)) {
          existing.push({
            id: 'h_' + item.t,
            query: item.q,
            keyword: '',
            answer: null,
            sources: null,
            timestamp: item.t,
            bookmarked: false,
            feedback: null,
          });
        }
      }
      saveHistoryList(existing);
      localStorage.removeItem(OLD_HISTORY_KEY);
    } catch { /* ignore corrupt data */ }
  }

  function addHistoryEntry(query, keyword) {
    const h = getHistory();
    // Remove duplicate query
    const idx = h.findIndex((i) => i.query === query);
    if (idx !== -1) h.splice(idx, 1);

    const entry = {
      id: 'h_' + Date.now(),
      query,
      keyword: keyword || '',
      answer: null,
      sources: null,
      timestamp: Date.now(),
      bookmarked: false,
      feedback: null,
    };
    h.unshift(entry);
    if (h.length > MAX_HISTORY) h.length = MAX_HISTORY;
    saveHistoryList(h);
    activeHistoryId = entry.id;
    renderSidebar();
    return entry.id;
  }

  function updateHistoryEntry(id, data) {
    const h = getHistory();
    const entry = h.find((i) => i.id === id);
    if (!entry) return;
    Object.assign(entry, data);
    if (entry.answer && entry.answer.length > MAX_ANSWER_STORE) {
      entry.answer = entry.answer.slice(0, MAX_ANSWER_STORE);
    }
    saveHistoryList(h);
  }

  function deleteHistoryEntry(id) {
    const h = getHistory().filter((i) => i.id !== id);
    saveHistoryList(h);
    if (activeHistoryId === id) {
      activeHistoryId = null;
      showWelcome();
    }
    renderSidebar();
  }

  function toggleBookmark(id) {
    const h = getHistory();
    const entry = h.find((i) => i.id === id);
    if (!entry) return;
    entry.bookmarked = !entry.bookmarked;
    saveHistoryList(h);
    renderSidebar();
  }

  function clearHistory() {
    if (sidebarTab === 'saved') {
      const h = getHistory().map((i) => ({ ...i, bookmarked: false }));
      saveHistoryList(h);
    } else {
      saveHistoryList([]);
    }
    activeHistoryId = null;
    showWelcome();
    renderSidebar();
  }

  function setFeedback(id, value) {
    const h = getHistory();
    const entry = h.find((i) => i.id === id);
    if (!entry) return;
    entry.feedback = entry.feedback === value ? null : value;
    saveHistoryList(h);
    updateFeedbackUI(entry.feedback);
  }

  /* ══════════════════════════════
     SIDEBAR RENDERING
     ══════════════════════════════ */

  function renderSidebar() {
    const list = $('#sidebar-list');
    const filterInput = $('#sidebar-filter');
    if (!list) return;

    const filter = filterInput ? filterInput.value.toLowerCase() : '';
    let items = getHistory();

    if (sidebarTab === 'saved') {
      items = items.filter((i) => i.bookmarked);
    }

    if (filter) {
      items = items.filter((i) => i.query.toLowerCase().includes(filter));
    }

    if (items.length === 0) {
      list.innerHTML = `<div class="sidebar-empty">${t(sidebarTab === 'saved' ? 'no_saved' : 'no_history')}</div>`;
      return;
    }

    list.innerHTML = items
      .map((item) => {
        const isActive = item.id === activeHistoryId;
        const ago = formatTimeAgo(item.timestamp);
        const qShort = item.query.length > 50 ? item.query.slice(0, 50) + '...' : item.query;
        return `
          <button class="sidebar-item${isActive ? ' active' : ''}" data-id="${item.id}" onclick="window.__app.loadHistoryItem('${item.id}')">
            <span class="sidebar-item-text">${escapeHtml(qShort)}</span>
            <span class="sidebar-item-time">${ago}</span>
            <span class="sidebar-item-actions">
              <button class="sidebar-item-btn${item.bookmarked ? ' bookmarked' : ''}" title="Bookmark" onclick="event.stopPropagation();window.__app.toggleBookmark('${item.id}')">
                ${item.bookmarked ? '★' : '☆'}
              </button>
              <button class="sidebar-item-btn" title="Delete" onclick="event.stopPropagation();window.__app.deleteHistoryEntry('${item.id}')">
                ✕
              </button>
            </span>
          </button>`;
      })
      .join('');
  }

  function setSidebarTab(tab) {
    sidebarTab = tab;
    $$('.sidebar-tab-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    renderSidebar();
  }

  /* ══════════════════════════════
     SIDEBAR TOGGLE (mobile)
     ══════════════════════════════ */

  function toggleSidebar() {
    const sidebar = $('.sidebar');
    const overlay = $('.sidebar-overlay');
    if (!sidebar) return;
    const isOpen = sidebar.classList.contains('open');
    sidebar.classList.toggle('open', !isOpen);
    if (overlay) overlay.classList.toggle('open', !isOpen);
  }

  function closeSidebar() {
    const sidebar = $('.sidebar');
    const overlay = $('.sidebar-overlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('open');
  }

  /* ══════════════════════════════
     WELCOME / RESULT STATE
     ══════════════════════════════ */

  function showWelcome() {
    const welcome = $('.welcome');
    const content = $('.content');
    const searchArea = $('.search-area');
    if (welcome) welcome.classList.remove('hidden');
    if (content) content.classList.add('hidden');
    if (searchArea) searchArea.classList.add('centered');

    // Reset
    activeHistoryId = null;
    rawMarkdown = '';
    const answerSection = $('#answer-section');
    const sourcesSection = $('#sources-section');
    const loading = $('#loading');
    if (answerSection) answerSection.classList.remove('visible');
    if (sourcesSection) sourcesSection.classList.remove('visible');
    if (loading) loading.classList.remove('visible');

    // Clear query
    const query = $('#query');
    if (query) query.value = '';
    const kw = $('#keyword');
    if (kw) kw.value = '';

    // Show examples
    const examples = $('#examples');
    if (examples) examples.style.display = '';

    renderSidebar();
  }

  function showResultState() {
    const welcome = $('.welcome');
    const content = $('.content');
    const searchArea = $('.search-area');
    if (welcome) welcome.classList.add('hidden');
    if (content) content.classList.remove('hidden');
    if (searchArea) searchArea.classList.remove('centered');
  }

  /* ══════════════════════════════
     MARKDOWN RENDERING
     ══════════════════════════════ */

  function renderMd(md) {
    const box = $('#answer-box');
    if (!box) return;
    let html = marked.parse(md);
    html = html.replace(/\[Источник:\s*([^\]]+)\]/g, '<span class="source-ref">[Источник: $1]</span>');
    box.innerHTML = html;
  }

  function renderMdStreaming(md) {
    const box = $('#answer-box');
    if (!box) return;
    let html = marked.parse(md);
    html = html.replace(/\[Источник:\s*([^\]]+)\]/g, '<span class="source-ref">[Источник: $1]</span>');
    box.innerHTML = html + '<span class="cursor-blink"></span>';
  }

  /* ══════════════════════════════
     FOLLOW-UP QUESTIONS
     ══════════════════════════════ */

  function extractFollowups(md) {
    return { answer: md, followups: [] };
  }

  function renderFollowups() {
    const container = $('#followup-chips');
    if (container) container.innerHTML = '';
  }

  /* ══════════════════════════════
     SOURCES
     ══════════════════════════════ */

  function cleanSourceName(filename) {
    return filename
      .replace(/^cyberleninka_/i, '')
      .replace(/^article_/i, '')
      .replace(/_/g, ' ')
      .replace(/\.pdf$/i, '');
  }

  function renderSources(sources) {
    const list = $('#sources-list');
    const section = $('#sources-section');
    const countEl = $('#sources-count');
    if (!list || !section) return;

    list.innerHTML = '';
    if (countEl) countEl.textContent = sources.length;

    sources.forEach((s, i) => {
      const pct = (s.score * 100).toFixed(1);
      let cls = 'score-low';
      if (s.score >= 0.6) cls = 'score-high';
      else if (s.score >= 0.4) cls = 'score-mid';

      const name = cleanSourceName(s.file);
      const preview = s.text ? escapeHtml(s.text.slice(0, 200)) + (s.text.length > 200 ? '...' : '') : '';

      const li = document.createElement('li');
      li.className = 'source-card';
      li.innerHTML = `
        <div class="source-card-top">
          <span class="source-num">${i + 1}</span>
          <span class="source-name" title="${escapeHtml(s.file)}">${escapeHtml(name)}</span>
          <span class="source-page">${t('page')} ${s.page}</span>
          <span class="source-score ${cls}">${pct}%</span>
        </div>
        ${preview ? `<div class="source-preview">${preview}</div>` : ''}`;

      li.addEventListener('click', () => {
        const prev = li.querySelector('.source-preview');
        if (prev) {
          prev.classList.toggle('expanded');
          if (prev.classList.contains('expanded')) {
            prev.textContent = s.text || '';
          }
        }
      });

      list.appendChild(li);
    });

    if (sources.length > 0) {
      section.classList.add('visible');
      list.classList.add('open');
      const toggle = $('#sources-toggle');
      if (toggle) toggle.classList.add('open');
    }
  }

  function toggleSourcesList() {
    const list = $('#sources-list');
    const toggle = $('#sources-toggle');
    if (list) list.classList.toggle('open');
    if (toggle) toggle.classList.toggle('open');
  }

  /* ══════════════════════════════
     SEARCH & SSE
     ══════════════════════════════ */

  function abortCurrent() {
    if (currentController) {
      currentController.abort();
      currentController = null;
    }
    if (loadingInterval) {
      clearInterval(loadingInterval);
      loadingInterval = null;
    }
    isStreaming = false;
  }

  async function doSearch(e) {
    if (e) e.preventDefault();

    const q = $('#query').value.trim();
    const kw = $('#keyword') ? $('#keyword').value.trim() : '';
    if (!q) return;

    abortCurrent();
    showResultState();
    closeSidebar();

    const answerSection = $('#answer-section');
    const answerBox = $('#answer-box');
    const answerFooter = $('#answer-footer');
    const sourcesSection = $('#sources-section');
    const sourcesList = $('#sources-list');
    const loading = $('#loading');
    const loadingText = $('#loading-text');
    const loadingTimer = $('#loading-timer');
    const btn = $('#submit-btn');
    const btnText = $('#btn-text');
    const followupChips = $('#followup-chips');

    // Reset
    rawMarkdown = '';
    if (answerBox) answerBox.innerHTML = '';
    if (answerSection) answerSection.classList.remove('visible');
    if (answerFooter) answerFooter.classList.remove('visible');
    if (sourcesSection) sourcesSection.classList.remove('visible');
    if (sourcesList) { sourcesList.innerHTML = ''; sourcesList.classList.remove('open'); }
    if (followupChips) followupChips.innerHTML = '';
    const sourcesToggle = $('#sources-toggle');
    if (sourcesToggle) sourcesToggle.classList.remove('open');

    // Hide examples
    const examples = $('#examples');
    if (examples) examples.style.display = 'none';

    // Show loading
    if (loading) loading.classList.add('visible');
    if (loadingText) loadingText.textContent = t('loading_text');
    if (btn) btn.disabled = true;
    if (btnText) btnText.textContent = t('searching');
    isStreaming = true;

    // Timer
    const startTime = Date.now();
    if (loadingTimer) loadingTimer.textContent = '0.0 с';
    loadingInterval = setInterval(() => {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      if (loadingTimer) loadingTimer.textContent = elapsed + ' с';
    }, 100);

    // Add to history
    const historyId = addHistoryEntry(q, kw);
    let collectedSources = [];

    const controller = new AbortController();
    currentController = controller;

    try {
      const params = new URLSearchParams({ q });
      if (kw) params.set('keyword', kw);

      const resp = await fetch('/api/answer?' + params, { signal: controller.signal });
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();

      if (loading) loading.classList.remove('visible');
      if (loadingInterval) { clearInterval(loadingInterval); loadingInterval = null; }
      if (answerSection) answerSection.classList.add('visible');

      answerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

      let buffer = '';
      let sourcesReceived = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith('event: sources')) {
            sourcesReceived = true;
            continue;
          }

          if (line.startsWith('event: done')) {
            isStreaming = false;
            // Extract follow-up questions
            const { answer, followups } = extractFollowups(rawMarkdown);
            renderMd(answer);
            renderFollowups(followups);
            if (answerFooter) answerFooter.classList.add('visible');
            // Save to history
            updateHistoryEntry(historyId, {
              answer: rawMarkdown,
              sources: collectedSources,
            });
            continue;
          }

          if (line.startsWith('event: error')) {
            continue;
          }

          if (line.startsWith('data: ')) {
            const data = line.slice(6);

            if (sourcesReceived && data.startsWith('[')) {
              try {
                collectedSources = JSON.parse(data);
                renderSources(collectedSources);
                sourcesReceived = false;
                continue;
              } catch { /* not JSON */ }
              sourcesReceived = false;
            }

            if (data !== '[DONE]') {
              rawMarkdown += data;
              renderMdStreaming(rawMarkdown);
            }
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        if (loading) loading.classList.remove('visible');
        if (loadingInterval) { clearInterval(loadingInterval); loadingInterval = null; }
        if (answerSection) answerSection.classList.add('visible');
        if (answerBox) answerBox.innerHTML = `<p style="color:var(--error)">${t('error_connection')}: ${escapeHtml(err.message)}</p>`;
      }
    }

    // Cleanup
    isStreaming = false;
    if (loadingInterval) { clearInterval(loadingInterval); loadingInterval = null; }
    if (loading) loading.classList.remove('visible');
    currentController = null;
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = t('search_btn');

    const leftover = answerBox ? answerBox.querySelector('.cursor-blink') : null;
    if (leftover) leftover.remove();

    // Update feedback UI
    const entry = getHistory().find((e) => e.id === historyId);
    updateFeedbackUI(entry ? entry.feedback : null);
  }

  /* ══════════════════════════════
     LOAD HISTORY ITEM
     ══════════════════════════════ */

  function loadHistoryItem(id) {
    const h = getHistory();
    const entry = h.find((i) => i.id === id);
    if (!entry) return;

    abortCurrent();
    closeSidebar();
    activeHistoryId = id;
    renderSidebar();

    // Populate query
    const query = $('#query');
    const keyword = $('#keyword');
    if (query) query.value = entry.query;
    if (keyword) keyword.value = entry.keyword || '';

    if (entry.answer) {
      // We have a stored answer — display it
      showResultState();
      rawMarkdown = entry.answer;

      const { answer, followups } = extractFollowups(rawMarkdown);
      renderMd(answer);
      renderFollowups(followups);

      const answerSection = $('#answer-section');
      const answerFooter = $('#answer-footer');
      if (answerSection) answerSection.classList.add('visible');
      if (answerFooter) answerFooter.classList.add('visible');

      if (entry.sources && entry.sources.length > 0) {
        renderSources(entry.sources);
      }

      updateFeedbackUI(entry.feedback);
    } else {
      // No stored answer — re-search
      doSearch();
    }
  }

  /* ══════════════════════════════
     FEEDBACK UI
     ══════════════════════════════ */

  function updateFeedbackUI(feedback) {
    const up = $('#feedback-up');
    const down = $('#feedback-down');
    if (up) {
      up.classList.toggle('up-active', feedback === 'up');
    }
    if (down) {
      down.classList.toggle('down-active', feedback === 'down');
    }
  }

  /* ══════════════════════════════
     COPY & EXPORT
     ══════════════════════════════ */

  function copyAnswer() {
    const box = $('#answer-box');
    if (!box) return;
    navigator.clipboard.writeText(box.innerText).then(() => showToast(t('copied')));
  }

  function copyMarkdown() {
    const { answer } = extractFollowups(rawMarkdown);
    navigator.clipboard.writeText(answer).then(() => showToast(t('copied')));
  }

  function downloadFile(filename, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportMd() {
    const q = $('#query') ? $('#query').value : 'query';
    const { answer } = extractFollowups(rawMarkdown);
    const content = `# ${q}\n\n${answer}\n`;
    const safeName = q.slice(0, 40).replace(/[^a-zA-Zа-яА-ЯёЁ0-9 ]/g, '').trim().replace(/ +/g, '_');
    downloadFile(`${safeName || 'answer'}.md`, content, 'text/markdown;charset=utf-8');
    toggleExportMenu();
  }

  function exportTxt() {
    const q = $('#query') ? $('#query').value : 'query';
    const box = $('#answer-box');
    const text = box ? box.innerText : '';
    const content = `Вопрос: ${q}\n\n${text}\n\nДата: ${new Date().toLocaleString()}\nИсточник: KKSON RAG\n`;
    const safeName = q.slice(0, 40).replace(/[^a-zA-Zа-яА-ЯёЁ0-9 ]/g, '').trim().replace(/ +/g, '_');
    downloadFile(`${safeName || 'answer'}.txt`, content, 'text/plain;charset=utf-8');
    toggleExportMenu();
  }

  function toggleExportMenu() {
    exportMenuOpen = !exportMenuOpen;
    const menu = $('#export-menu');
    if (menu) menu.classList.toggle('open', exportMenuOpen);
  }

  /* ══════════════════════════════
     TOAST
     ══════════════════════════════ */

  function showToast(msg) {
    const t = $('#toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2000);
  }

  /* ══════════════════════════════
     SHORTCUTS MODAL
     ══════════════════════════════ */

  function toggleShortcutsModal() {
    const overlay = $('#shortcuts-modal');
    if (overlay) overlay.classList.toggle('visible');
  }

  /* ══════════════════════════════
     KEYBOARD SHORTCUTS
     ══════════════════════════════ */

  function initShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Ctrl+Enter — submit
      if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault();
        doSearch();
        return;
      }
      // Ctrl+D — theme
      if (e.ctrlKey && e.key === 'd') {
        e.preventDefault();
        toggleTheme();
        return;
      }
      // Ctrl+K or / — focus search (when not in input)
      if ((e.ctrlKey && e.key === 'k') || (e.key === '/' && !isInputFocused())) {
        e.preventDefault();
        const q = $('#query');
        if (q) q.focus();
        return;
      }
      // Ctrl+H — toggle sidebar (mobile)
      if (e.ctrlKey && e.key === 'h') {
        e.preventDefault();
        toggleSidebar();
        return;
      }
      // ? — shortcuts help (when not in input)
      if (e.key === '?' && !isInputFocused()) {
        toggleShortcutsModal();
        return;
      }
      // Escape
      if (e.key === 'Escape') {
        const modal = $('#shortcuts-modal');
        if (modal && modal.classList.contains('visible')) {
          modal.classList.remove('visible');
          return;
        }
        if (exportMenuOpen) {
          toggleExportMenu();
          return;
        }
        closeSidebar();
      }
    });
  }

  function isInputFocused() {
    const el = document.activeElement;
    return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA');
  }

  /* ══════════════════════════════
     AUTO-RESIZE TEXTAREA
     ══════════════════════════════ */

  function initTextareaResize() {
    const textarea = $('#query');
    if (!textarea) return;
    textarea.addEventListener('input', () => {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    });
  }

  /* ══════════════════════════════
     CLOSE EXPORT ON OUTSIDE CLICK
     ══════════════════════════════ */

  function initClickOutside() {
    document.addEventListener('click', (e) => {
      if (exportMenuOpen && !e.target.closest('.export-dropdown')) {
        exportMenuOpen = false;
        const menu = $('#export-menu');
        if (menu) menu.classList.remove('open');
      }
    });
  }

  /* ══════════════════════════════
     UTILS
     ══════════════════════════════ */

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  function formatTimeAgo(ts) {
    const diff = Date.now() - ts;
    if (diff < 60000) return getLang() === 'en' ? 'now' : 'сейчас';
    if (diff < 3600000) return Math.floor(diff / 60000) + (getLang() === 'en' ? 'm' : ' мин');
    if (diff < 86400000) return Math.floor(diff / 3600000) + (getLang() === 'en' ? 'h' : ' ч');
    return new Date(ts).toLocaleDateString(getLang() === 'en' ? 'en' : 'ru');
  }

  /* ══════════════════════════════
     INIT
     ══════════════════════════════ */

  function init() {
    // Theme
    setTheme(getTheme());

    // Migrate old history
    migrateOldHistory();

    // i18n
    applyI18n();

    // Sidebar
    renderSidebar();

    // Configure marked
    marked.setOptions({ breaks: true, gfm: true });

    // Textarea auto-resize
    initTextareaResize();

    // Shortcuts
    initShortcuts();

    // Click outside
    initClickOutside();

    // Example chips
    $$('.example-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const q = $('#query');
        if (q) {
          q.value = chip.textContent;
          q.focus();
        }
      });
    });

    // Search form
    const form = $('#search-form');
    if (form) form.addEventListener('submit', doSearch);

    // Ctrl+Enter from textarea
    const textarea = $('#query');
    if (textarea) {
      textarea.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'Enter') {
          e.preventDefault();
          doSearch();
        }
      });
    }

    // Lang buttons
    $$('.lang-option').forEach((btn) => {
      btn.addEventListener('click', () => setLang(btn.dataset.lang));
      btn.classList.toggle('active', btn.dataset.lang === getLang());
    });
  }

  /* ══════════════════════════════
     PUBLIC API
     ══════════════════════════════ */

  window.__app = {
    toggleTheme,
    toggleSidebar,
    closeSidebar,
    showWelcome,
    doSearch,
    loadHistoryItem,
    deleteHistoryEntry,
    toggleBookmark,
    clearHistory,
    setSidebarTab,
    toggleSourcesList,
    copyAnswer,
    copyMarkdown,
    exportMd,
    exportTxt,
    toggleExportMenu,
    toggleShortcutsModal,
    setFeedback,
    setLang,
    _getActiveId: () => activeHistoryId,
  };

  // Boot
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

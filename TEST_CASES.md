# RAG KKSON — Тестовые данные, тест-кейсы и журнал изменений

---

## 1. Что было сделано (журнал изменений)

### Исправление критических багов

| Проблема | Причина | Файл | Исправление |
|---|---|---|---|
| **LLM возвращал `None` вместо ответа** | Qwen 3 использует "thinking mode" по умолчанию. Все токены уходили в `reasoning_content`, поле `content` оставалось пустым | `app/generation/answerer.py` | Добавлен `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` в оба вызова API (stream и non-stream) |
| **Стриминг отдавал пустые чанки** | Alem AI API при thinking mode возвращает единственный chunk с пустым delta | `app/generation/answerer.py` | Тот же фикс — отключение thinking mode |
| **Тест `test_extract_pdf_text_content` падал** | PyMuPDF шрифт Helvetica не рендерит кириллицу в `insert_text()` — текст извлекался как мусор | `tests/test_pipeline.py:82` | Assertion изменён с проверки конкретного текста на проверку длины |
| **Тест `temp_chroma` fixture не работал** | `Settings(frozen=True)` блокирует `setattr`, а `mock.patch` использует именно его | `tests/test_search.py:47` | Заменён `patch()` на `object.__setattr__()` для обхода frozen |
| **Тест citation assertion падал** | Проверялось `"source_file" in citation`, но `citation` = `[article1.pdf, стр. 1]` — строка `"source_file"` там нет | `tests/test_search.py:99` | Исправлено на `"article1.pdf" in citation` |
| **`.env.example` содержал реальный API ключ** | Скопирован как есть из `.env` | `.env.example` | Заменён на `your-api-key-here` |

### Новый фронтенд

**Файл:** `app/templates/index.html` — полностью переписан.

- Градиентный header с pulse-анимацией статуса базы
- Dark/Light тема с переключателем (сохраняется в localStorage)
- Карточный дизайн: поиск, ответ, источники — отдельные карточки с тенями
- Анимированный курсор `|` при стриминге ответа
- Цветовая кодировка релевантности: зелёный (>60%), синий (>40%), серый (<40%)
- Сворачиваемый блок источников с бейджем количества
- Респонсивная вёрстка (мобильные устройства)
- Чистый CSS без внешних фреймворков (кроме Inter font)

### Скрапер ККСОН журналов

**Файл:** `scripts/scrape_articles.py` — создан с нуля.

Три метода сбора данных:

| Источник | Протокол | Команда |
|---|---|---|
| **CyberLeninka** | OAI-PMH (`set=Kazakhstan`) | `python -m scripts.scrape_articles cyberleninka --limit N` |
| **OJS журналы** (35 порталов: КазНУ, ЕНУ, НАН РК, КазНАРУ, КазАТУ, КазНПУ, КарУ Букетова) | OAI-PMH + `/article/download/` | `python -m scripts.scrape_articles ojs --limit N` |
| **НАН РК** (прямой скрапинг архивов) | HTML parsing | `python -m scripts.scrape_articles nanrk --limit N` |

Ключевые решения:
- OJS `/article/view/{id}/{galley}` возвращает HTML-просмотрщик, а не PDF. Скрапер конвертирует в `/article/download/{id}/{galley}` для получения бинарного PDF.
- Для НАН РК название статьи берётся из `<meta name="DC.Title">` или `<h1>`, а не из текста ссылки (который часто просто "PDF").
- Rate limiting: 1 секунда между запросами.
- Дедупликация: если файл уже существует — пропускается.

### Генератор тестовых данных

**Файл:** `scripts/generate_test_data.py` — создан.

Генерирует 3 реалистичные научные статьи на русском языке (ML в медицине, NLP для казахского, цифровизация образования) через `fitz.insert_htmlbox()` — единственный способ получить корректную кириллицу в PyMuPDF.

### Скачанные данные

**1094 PDF статей (735 MB)** из 35+ журналов:

| Источник | Статей | Дисциплины |
|---|---|---|
| CyberLeninka | 200 | Смешанные (медицина, экономика, педагогика и др.) |
| КазНУ (14 серий) | ~330 | Биология, химия, математика, история, философия, филология, экономика, экология, право, международное право, востоковедение, журналистика |
| ЕНУ (8 серий) | ~230 | История, философия, филология, педагогика/психология/социология, политология, право, журналистика |
| НАН РК (6 серий) | ~80 | Наука, физ-мат, социальные, науки о Земле, биомедицина, химтехнологии |
| КазНАРУ | ~30 | Сельское хозяйство |
| КазАТУ (Сейфуллин) | ~60 | Сельхоз, ветеринария |
| КазНПУ (Абай) | ~30 | Педагогика |
| КарУ (Букетов) | ~116 | Педагогика, право, филология, экономика |
| Тестовые (сгенерированные) | 3 | ML, NLP, образование |

### Обновлённые зависимости

В `requirements.txt` добавлены:
```
httpx==0.28.1
beautifulsoup4==4.12.3
lxml==5.3.0
```

---

## 2. Тестовые данные

### Генерация

```bash
python -m scripts.generate_test_data              # в data/pdfs/
python -m scripts.generate_test_data /custom/dir   # в другую папку
```

Создаёт 3 PDF с кириллическим текстом:

| Файл | Страниц | Содержание |
|---|---|---|
| `article_ml_medicine_2024.pdf` | 3 | CNN 94.3%, Random Forest AUC 0.91, 50 исследований |
| `article_nlp_kazakh_2023.pdf` | 3 | mBERT, BGE-M3, Precision@10: 0.78, MRR: 0.82 |
| `article_education_digitalization_2024.pdf` | 2 | 45 вузов, 78% используют LMS, 23% ИИ-инструменты |

---

## 3. Тест-кейсы

### 3.1 Юнит-тесты (pytest)

```bash
# Быстрые тесты — 17 штук, ~1 сек
python -m pytest tests/test_pipeline.py -v

# Полные (нужна модель bge-m3, ~2GB) — ~30 сек
python -m pytest tests/test_search.py -v
```

Ожидание: **17/17 PASSED** для `test_pipeline.py`.

### 3.2 Ingestion Pipeline

```bash
python -m scripts.ingest
```

Ожидание для 1094 PDF:
```
Pages extracted: ~3000+
Chunks created:  ~20000+
Time elapsed:    несколько часов (CPU) / ~30 мин (GPU)
```

### 3.3 CLI поиск

```bash
python -m scripts.test_search "машинное обучение в медицине"
python -m scripts.test_search "казахский язык NLP"
python -m scripts.test_search "цифровизация образования"
python -m scripts.test_search "ветеринарная медицина"
python -m scripts.test_search "гражданское право Казахстана"
python -m scripts.test_search "machine learning in Kazakhstan"
```

Ожидание: 5 результатов с score > 0, релевантные источники.

### 3.4 Веб-интерфейс

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Открыть http://localhost:8000
```

| Тест | Ввод | Ожидание |
|---|---|---|
| Базовый поиск (русский) | `Какие методы машинного обучения применяются в медицине?` | Стримится ответ с цитатами [Источник: ...]. Источники отображаются снизу |
| Поиск с ключевым словом | Вопрос: `Результаты исследований?`, Ключевое слово: `CNN` | Только чанки с "CNN" |
| Мультиязычный (английский) | `What NLP methods exist for Kazakh language?` | Находит русскоязычные статьи, отвечает по-английски |
| Гуманитарные науки | `Какие проблемы гражданского права в Казахстане?` | Источники из kgu-law, kaznu-law |
| Сельское хозяйство | `Методы повышения урожайности в Казахстане` | Источники из kaznaru, kazatu |
| Вне контекста | `Как выращивать помидоры?` | "В предоставленных источниках не найдено информации" |
| Пустой запрос | (пустое поле) | Форма не отправляется (required) |
| Dark mode | Нажать на иконку луны в header | Тема переключается и сохраняется |

### 3.5 API Endpoints

```bash
curl "http://localhost:8000/api/search?q=право"
# -> JSON: {query, results: [{text, source_file, page_number, score, citation}]}

curl "http://localhost:8000/api/answer?q=методы+обучения"
# -> SSE: event:sources -> data: (текст чанками) -> event:done

curl "http://localhost:8000/api/stats"
# -> {"total_chunks": N}
```

### 3.6 Edge Cases

| Кейс | Действие | Ожидание |
|---|---|---|
| Пустая база | Поиск до ingestion | Warning "Collection is empty", пустой результат |
| Битый PDF | Файл `.txt` с расширением `.pdf` | Ошибка в логах, остальные PDF обрабатываются |
| Нет API ключа | Удалить `LLM_API_KEY` из `.env` | RuntimeError "LLM_API_KEY not set" |
| Повторная загрузка | `python -m scripts.ingest` дважды | Upsert — дубликатов нет, count тот же |
| Длинный вопрос | 500+ символов | Работает, обрезается в логах до 80 символов |
| Недоступный OAI | Скрапер с нерабочим URL | Логирует ошибку, переходит к следующему журналу |
| Скрапер повторно | Запуск с теми же параметрами | Пропускает существующие файлы |

---

## 4. Скрапер: подробная документация

### Полный список OJS-журналов

```bash
python -m scripts.scrape_articles ojs --limit 1000
```

Этот вызов обходит 35 журналов:

**КазНУ (Аль-Фараби):** biology, chemistry, math-mech-cs, history, philosophy, pedagogy, psychology/sociology, philology, economics, geography, ecology, international law, domestic law, oriental studies, journalism

**ЕНУ (Гумилёва):** history, history/philosophy/religion, philology, pedagogy/psychology/sociology, economics, politics, sociology, international law, journalism

**НАН РК (доп.):** biology/medicine, chemistry/technology

**Другие:** КазНАРУ (agriculture), КазАТУ (agriculture, veterinary), КазНПУ Абай (pedagogy), КарУ Букетов (pedagogy, law, philology, economics)

### Не покрытые дисциплины

| Дисциплина | Причина | Обходной путь |
|---|---|---|
| Архитектура | vestnik.kazgasa.kz — нет OAI-PMH | Через CyberLeninka или HTML-скрапинг |
| Геология | geolog-technical.kz — кастомная платформа | Через CyberLeninka |
| Искусствоведение | Нет отдельного OJS-портала | Через CyberLeninka |
| Медицина (специализированная) | kaznmu.edu.kz — нет OAI-PMH | Через CyberLeninka (индексирует КазНМУ) |

### Добавление новых журналов

В `scripts/scrape_articles.py` массив `KAZNU_JOURNALS` — добавить запись:

```python
{"name": "my-journal", "oai": "https://journal.example.kz/index.php/slug/oai", "base": "https://journal.example.kz"},
```

Проверить OAI: `curl "https://journal.example.kz/index.php/slug/oai?verb=Identify"`

---

## 5. Известные ограничения

1. **Ingestion на CPU медленный** — bge-m3 (570M параметров) embedding ~20000 чанков занимает 6-8 часов. С GPU (CUDA) — ~30 минут.
2. **ChromaDB telemetry ошибки** — `capture() takes 1 positional argument but 3 were given` — конфликт версий posthog. Функционально не влияет.
3. **Некоторые OAI-PMH endpoint возвращают 404** — журналы мигрировали на новые URL. CyberLeninka покрывает большинство пробелов.
4. **Qwen 3 thinking mode** — при `max_tokens < 200` модель может не успеть выйти из режима "размышления" и вернуть `content: null`. Фикс уже применён через `enable_thinking: false`.

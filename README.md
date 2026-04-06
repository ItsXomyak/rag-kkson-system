# RAG KKSON — Поиск по научным журналам Казахстана

RAG-система для поиска и анализа научных статей из журналов, рекомендованных ККСОН МОН РК (КОКНВО).
Аналог [answerthis.io](https://answerthis.io), заточенный под казахстанскую науку.

**Стек:** Python 3.11+ / FastAPI / ChromaDB / bge-m3 / Qwen 3 (Alem AI) / HTMX

---

## Быстрый старт

```bash
# 1. Окружение
python -m venv .venv && source .venv/Scripts/activate   # Windows
# или: source .venv/bin/activate                        # Linux/Mac
pip install -r requirements.txt


# на моем ноуте
python -m venv .venv                                                                                  .venv/Scripts/activate  # Windows-specific activation                                               
python -m pip install -r requirements.txt

# 2. Настройка
cp .env.example .env
# Отредактируй .env — впиши свой LLM_API_KEY от Alem AI

# 3. Скачай статьи ККСОН (автоматически)
python -m scripts.scrape_articles all --limit 500

# 4. Загрузи в базу
python -m scripts.ingest
# Первый запуск скачает модель bge-m3 (~2GB), потом кеширует

# 5. Запусти сервер
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Открой http://localhost:8000
```

---

## Архитектура

```
Пользователь
    |
    v
[FastAPI + HTMX]  <-- веб-интерфейс (dark/light тема)
    |
    |-- /api/search  --> [ChromaDB] hybrid search (semantic + keyword)
    |                        ^
    |                        | embeddings (bge-m3, локально на CPU)
    |                        |
    |                  [PDF -> chunks -> vectors]
    |
    +-- /api/answer  --> [Qwen 3 API] streaming генерация с цитированием
```

### Файловая структура

```
rag-kkson/
|-- app/
|   |-- main.py              # FastAPI приложение + SSE стриминг
|   |-- config.py             # Настройки из .env
|   |-- ingestion/
|   |   |-- pdf_parser.py     # PDF -> текст (PyMuPDF)
|   |   |-- chunker.py        # Текст -> чанки (RecursiveCharacterTextSplitter)
|   |   +-- embedder.py       # Чанки -> эмбеддинги -> ChromaDB
|   |-- retrieval/
|   |   +-- search.py         # Гибридный поиск (semantic + keyword)
|   |-- generation/
|   |   +-- answerer.py       # Генерация ответа через Qwen 3 (Alem AI)
|   +-- templates/
|       +-- index.html        # Фронтенд (HTMX + PicoCSS, dark/light)
|-- scripts/
|   |-- ingest.py             # CLI загрузки PDF в базу
|   |-- test_search.py        # CLI тест поиска
|   |-- scrape_articles.py    # Скрапер статей ККСОН (3 источника)
|   +-- generate_test_data.py # Генератор тестовых PDF
|-- tests/
|   |-- test_pipeline.py      # 17 тестов: парсинг, чанкинг, интеграция
|   +-- test_search.py        # Тесты эмбеддингов и поиска (slow)
|-- data/pdfs/                # PDF статей (сюда кладутся файлы)
|-- chroma_db/                # ChromaDB хранилище (автосоздаётся)
|-- requirements.txt
|-- Dockerfile
|-- docker-compose.yml
+-- .env.example
```

---

## Источники статей ККСОН

### Автоматический скрапинг

Скрапер покрывает **100% перечня КОКСНВО** (121 журнал):
- **102 OJS-журнала** через OAI-PMH (40+ учреждений)
- **19 не-OJS журналов** через кастомные скраперы (Торайғыров, ҚарТУ, ҚазҰМУ, КазГАСА, Bilig, WordPress-журналы)
- **CyberLeninka** как дополнительный источник

```bash
# Все источники сразу (CyberLeninka + 102 OJS + НАН РК HTML + кастомные)
python -m scripts.scrape_articles all --limit 3000

# Или по отдельности:
python -m scripts.scrape_articles cyberleninka --limit 200
python -m scripts.scrape_articles ojs --limit 1500    # 102 журнала из 40+ учреждений
python -m scripts.scrape_articles nanrk --limit 100
```

### Покрытие дисциплин (102 OJS-журнала + CyberLeninka)

| Учреждение / Портал | Дисциплины | Журналов |
|---|---|---|
| **CyberLeninka** (OAI-PMH, set=Kazakhstan) | Все направления (смешанные) | ~тысячи |
| **КазНУ (Аль-Фараби)** | Биология, химия, математика, физика, экология, география, история, философия, филология, экономика, право, международное право, востоковедение, журналистика, дінтану + 3 англоязычных | 20 |
| **ЕНУ (Гумилёва)** | История, философия, филология, педагогика/психология, экономика, политология, социология, право, журналистика, биология, математика/CS, техника + 2 англоязычных | 15 |
| **НАН РК** | Наука, физ-мат, социальные/гуманитарные, науки о Земле, биомедицина, химтехнологии, экономика, доклады | 8 |
| **Абай КазНПУ** | Педагогика, психология, история, физ-мат, филология, спецпедагогика, естествознание/география, педагогика-психология | 8 |
| **Караганда (Букетов)** | Педагогика, право, филология, экономика, история/философия, биомедицина/география, физика | 7 |
| **Сельское хозяйство** | КазНАРУ, КазАТУ (2 серии), ЗКАТУ Жәңгір хан | 4 |
| **Абылай хан ҚазХҚ** | Международные отношения, филология, педагогика | 3 |
| **КИСЭ/КАЗИСС** | Қоғам және дәуір, Қазақстан-Спектр, Central Asia's Affairs | 3 |
| **Сатпаев (КазНТУ)** | Инженерия, металлургия | 1 |
| **Семей мед. университет** | Медицина | 1 |
| **Ясауи университеті** | Вестник, филология | 2 |
| **АУЭС** | Энергетика, байланыс | 1 |
| **Astana IT University** | IT, коммуникации | 1 |
| **ВКТУ Серікбаев** | Инженерия, цифровые гуманитарные | 2 |
| **Қостанай (Байтұрсынов)** | Сельское хозяйство, ветеринария | 1 |
| **Қоркыт Ата Қызылорда** | Аграрные науки | 1 |
| **Еуразия гуманитарлық** | Филология | 1 |
| **НИИ и академии** | Философия (2), литература/өнер, искусство, металлургия, горение/плазмохимия, биотехнология, химия, история, онкология, репродуктивная медицина, здравоохранение, спорт, госуправление | 14 |
| **NEICON/Elpub OJS** | Нархоз (экономика), АТУ (технология), Тұран, ҰЯО (ядерная физика), UIB (бизнес), КИСЭ (экономика), агрорынок, КЕУ, нефть/газ | 9 |

### Кастомные скраперы для не-OJS журналов

```bash
python -m scripts.scrape_articles custom --limit 200
```

| Учреждение | Платформа | Скрапер |
|---|---|---|
| Торайғыров университеті (10 серий) | Custom Laravel | `scrape_toraighyrov` |
| ҚарТУ «Труды университета» (4 серии) | Custom Laravel | `scrape_kartu` |
| ҚазҰМУ Асфендияров | Custom PHP | `scrape_kaznmu` |
| ҚазБСҚА/КазГАСА (архитектура) | Yii Framework | `scrape_kazgasa` |
| Bilig (Ясауи) | DergiPark | `scrape_bilig` |
| «Қазақстан фармациясы» | WordPress | `scrape_wordpress` |
| «Горный журнал Казахстана» | WordPress | `scrape_wordpress` |
| ҰИА (Нац. инженерная академия) | WordPress | `scrape_wordpress` |
| DKU CAJWR | WordPress | `scrape_wordpress` |
| edu.e-history.kz | Custom (SSL expired) | `scrape_ehistory` |

---

## API

| Endpoint | Метод | Описание |
|---|---|---|
| `/` | GET | Веб-интерфейс |
| `/api/search?q=...&keyword=...` | GET | Поиск по базе (JSON) |
| `/api/answer?q=...&keyword=...` | GET | Стриминг ответа (SSE) |
| `/api/stats` | GET | Статистика коллекции |

---

## Деплой на VPS

### Hetzner CX22 (2 vCPU, 4GB RAM, ~5 EUR/мес)

```bash
# 1. На сервере: установи Docker
ssh root@<ip>
curl -fsSL https://get.docker.com | sh

# 2. Залей проект
rsync -avz --exclude '.venv' --exclude 'model_cache' --exclude 'chroma_db' \
  ./rag-kkson/ root@<ip>:/opt/rag-kkson/

# 3. Настрой и запусти
cd /opt/rag-kkson
cp .env.example .env && nano .env
docker compose up -d --build

# 4. Скачай статьи и загрузи в базу
docker compose exec rag python -m scripts.scrape_articles all --limit 500
docker compose exec rag python -m scripts.ingest
```

### Стоимость

| Компонент | Стоимость |
|---|---|
| VPS (Hetzner CX22) | ~5 EUR/мес |
| Embedding модель (bge-m3) | Бесплатно |
| ChromaDB | Бесплатно |
| Qwen 3 API (Alem AI) | Бесплатно |
| **Итого** | **~5 EUR/мес** |

---

## Тесты

```bash
# Быстрые (PDF парсинг, чанкинг) — 17 тестов, ~1 сек
python -m pytest tests/test_pipeline.py -v

# Полные (с эмбеддингами, нужна модель ~2GB) — ~30 сек
python -m pytest tests/ -v
```

---

## Масштабирование

- **Больше статей** -> VPS с 8GB RAM (CX32, ~10 EUR/мес)
- **Быстрее embedding** -> GPU сервер или pre-computed embeddings
- **Точнее поиск** -> добавить reranker (cross-encoder)
- **Удобнее** -> загрузка PDF через веб-интерфейс

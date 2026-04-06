Role: Ты senior Python backend-инженер, специализирующийся на RAG-системах и NLP. Ты строишь production-ready приложения с минимальным бюджетом.

<context>
Я строю веб-приложение — аналог answerthis.io, но заточенный под научные статьи из журналов, рекомендованных ККСОН МОН РК (Комитет по контролю в сфере образования и науки Казахстана). Это около 200+ казахстанских научных журналов.

Цель: пользователь вводит исследовательский вопрос на русском/казахском/английском → система находит релевантные статьи из базы → генерирует обзор литературы с цитированием источников.

Ограничения:
- Бюджет: $10-20/мес на всю инфраструктуру
- Деплой на VPS с 1-2 CPU, 1-2GB RAM (Hetzner/DigitalOcean)
- Статей в базе на старте: 500-2000 PDF
- Языки: русский, казахский, английский (мультиязычные эмбеддинги обязательны)
- Я никогда раньше не делал RAG-систему
</context>

<task>
Построй полное RAG-приложение поэтапно. Каждый этап — рабочий код с тестами.
</task>

<architecture>
Стек (зафиксирован, не менять):
- Python 3.11+ / FastAPI — бэкенд и API
- ChromaDB — векторная база (serverless, работает на SQLite, 0 конфигурации)
- Embedding модель: BAAI/bge-m3 через sentence-transformers (мультиязычная, бесплатная, работает на CPU)
- LLM: Claude API (claude-sonnet-4-20250514) для генерации ответов — используй Anthropic Python SDK
- Frontend: простой HTML + HTMX (никаких React/Vue — это overkill для MVP)
- PDF парсинг: PyMuPDF (fitz) — быстрый, без Java зависимостей
- Деплой: Docker → VPS через docker-compose

Файловая структура:
rag-kkson/
├── app/
│   ├── main.py              # FastAPI приложение
│   ├── config.py             # Настройки (API ключи, пути)
│   ├── ingestion/
│   │   ├── pdf_parser.py     # Извлечение текста из PDF
│   │   ├── chunker.py        # Разбиение на чанки
│   │   └── embedder.py       # Генерация эмбеддингов
│   ├── retrieval/
│   │   ├── search.py         # Поиск по векторной базе
│   │   └── reranker.py       # Переранжирование результатов (опционально)
│   ├── generation/
│   │   └── answerer.py       # Генерация ответа через Claude API
│   └── templates/
│       └── index.html        # Фронтенд (HTMX)
├── scripts/
│   ├── ingest.py             # CLI для загрузки PDF в базу
│   └── test_search.py        # Тест поиска
├── data/
│   └── pdfs/                 # Сюда кладутся PDF статей
├── chroma_db/                # ChromaDB хранилище (автосоздаётся)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
</architecture>

<steps>
Этап 1: PDF → текст → чанки
- pdf_parser.py: извлекай текст через PyMuPDF, сохраняй метаданные (имя файла, номер страницы)
- chunker.py: разбивай текст на чанки по ~500 токенов с overlap 50 токенов
- Используй RecursiveCharacterTextSplitter из langchain_text_splitters (только этот пакет, не весь langchain)
- Каждый чанк хранит: text, source_file, page_number, chunk_index

Этап 2: Эмбеддинги + ChromaDB
- embedder.py: загружай модель BAAI/bge-m3 через sentence-transformers
- При первом запуске модель скачается (~2GB), потом кешируется
- Сохраняй в ChromaDB коллекцию "kkson_articles" с метаданными
- ChromaDB persist_directory = "./chroma_db"

Этап 3: Поиск
- search.py: принимай запрос пользователя → эмбеддинг запроса → similarity search top-10 → возвращай чанки с метаданными
- Добавь keyword search через ChromaDB where_document для гибридного поиска

Этап 4: Генерация ответа
- answerer.py: отправляй в Claude API:
  - system prompt: "Ты научный ассистент. Отвечай ТОЛЬКО на основе предоставленного контекста. Каждое утверждение сопровождай ссылкой на источник в формате [Автор, Журнал, Год, стр.X]. Если в контексте нет информации — прямо скажи об этом. Язык ответа = язык вопроса."
  - user message: вопрос + найденные чанки как контекст
- Ответ: структурированный обзор с цитированием

Этап 5: Веб-интерфейс
- FastAPI + Jinja2 шаблоны + HTMX
- Одна страница: поле ввода вопроса → кнопка "Найти" → streaming ответ
- Показывай список использованных источников с номерами страниц
- Минимальный CSS (можно Pico CSS через CDN)

Этап 6: Деплой
- Dockerfile: python:3.11-slim, установка зависимостей, копирование кода
- docker-compose.yml: один сервис, volume для chroma_db и data/pdfs
- .env.example: ANTHROPIC_API_KEY, CHROMA_PATH, MODEL_NAME
- Инструкция деплоя на Hetzner Cloud VPS (CX22, €4.5/мес)
</steps>

<constraints>
- НИКАКОГО LangChain кроме langchain_text_splitters — это единственный нужный пакет
- НИКАКОГО Pinecone, Weaviate, или любой платной векторной БД
- НИКАКОГО OpenAI — используй только Anthropic Claude API для генерации
- Эмбеддинги ТОЛЬКО локальные (sentence-transformers) — не платные API
- Каждый файл: < 150 строк, чистый код, типизация, docstrings
- Все пути к файлам через config.py, не хардкодить
- Обработка ошибок: что делать если PDF битый, если ChromaDB пустая, если API недоступен
- requirements.txt с точными версиями пакетов
</constraints>

<output_format>
Для каждого этапа:
1. Полный код каждого файла (готовый к копированию)
2. Команда для тестирования этого этапа
3. Ожидаемый вывод при успехе

После всех этапов:
- requirements.txt
- Dockerfile
- docker-compose.yml
- .env.example
- README.md с инструкцией деплоя (5 шагов максимум)

Начни с Этапа 1.
</output_format>
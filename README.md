# RAG KKSON: Retrieval-Augmented Generation System for Kazakhstan Scientific Journals

A retrieval-augmented generation (RAG) system for searching and analyzing scientific articles from 121 Kazakhstan journals recommended by the KKSON Committee (Ministry of Education and Science of the Republic of Kazakhstan).

The system enables researchers to query a database of 1094 scientific articles in Russian, Kazakh, and English, and receive structured answers with citations to specific sources and page numbers.

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [System Architecture](#system-architecture)
- [Technical Stack](#technical-stack)
- [Retrieval Pipeline](#retrieval-pipeline)
- [Installation](#installation)
- [Data Collection](#data-collection)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Evaluation Results](#evaluation-results)
- [Project Structure](#project-structure)
- [Deployment](#deployment)
- [Configuration](#configuration)
- [Testing](#testing)

---

## Problem Statement

Researchers working with Kazakhstan scientific literature face a challenge: relevant articles are scattered across 121 journals hosted on different platforms (OJS, custom CMS, CyberLeninka). Finding and synthesizing information on a given topic requires manually searching each journal.

**RAG KKSON** automates this process:

1. **Collects** articles from all 121 KKSON journals via automated scrapers
2. **Indexes** article content using multilingual vector embeddings
3. **Retrieves** relevant passages using semantic search with query expansion
4. **Generates** structured answers with source citations

---

## System Architecture

```
                          Query: "гражданское право Казахстана"
                                        |
                                        v
                        +-------------------------------+
                        |     1. QUERY EXPANSION        |
                        |   LLM generates 3 sub-queries |
                        |   for broader topic coverage   |
                        +-------------------------------+
                                        |
                           [original + 3 sub-queries]
                                        v
                        +-------------------------------+
                        |    2. MULTI-QUERY SEARCH       |
                        |  4 queries x 15 chunks each    |
                        |  + keyword supplementary search|
                        |  ChromaDB (cosine similarity)  |
                        +-------------------------------+
                                        |
                               [~22 unique chunks]
                                        v
                        +-------------------------------+
                        |   3. CROSS-ENCODER RERANKER   |
                        |   bge-reranker-v2-m3 scores   |
                        |   each (query, chunk) pair     |
                        |   Filters irrelevant results   |
                        +-------------------------------+
                                        |
                                [top-10 chunks]
                                        v
                        +-------------------------------+
                        |     4. ANSWER GENERATION      |
                        |   Qwen 3 LLM via Alem AI API  |
                        |   Streaming SSE response       |
                        |   Citations: [Source, Page N]  |
                        +-------------------------------+
                                        |
                                        v
                          Structured answer with sources
```

---

## Technical Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | FastAPI + Uvicorn | REST API, SSE streaming |
| **Vector DB** | ChromaDB (serverless) | Embedding storage & similarity search |
| **Embeddings** | BAAI/bge-m3 (1024-dim) | Multilingual text-to-vector (RU/KZ/EN) |
| **Reranker** | BAAI/bge-reranker-v2-m3 | Cross-encoder relevance scoring |
| **LLM** | Qwen 3 via Alem AI API | Answer generation with citations |
| **PDF Parsing** | PyMuPDF | Text extraction from scientific articles |
| **Chunking** | LangChain TextSplitter | 1500-char chunks with 150-char overlap |
| **Frontend** | HTML + CSS + Vanilla JS | SPA with SSE streaming, i18n, theming |
| **Deployment** | Docker + docker-compose | Containerized deployment |

---

## Retrieval Pipeline

### Embedding Model: bge-m3

**BAAI General Embedding** (Multi-lingual, Multi-granularity, Multi-functionality) is a 570M parameter model supporting 100+ languages. It converts text into 1024-dimensional vectors where semantically similar texts are close in vector space:

```
"гражданское право"  → [0.12, -0.34, 0.56, ...] (1024 dims)
"civil law"          → [0.11, -0.33, 0.55, ...]  ← similar vector
"квантовая физика"   → [-0.87, 0.21, -0.44, ...] ← distant vector
```

This enables **cross-lingual search**: a query in Kazakh retrieves articles written in Russian and English.

### Query Expansion

A single query produces a single embedding vector, which captures only one "direction" in vector space. For broad queries like "education in Kazakhstan", this misses articles about specific sub-topics.

**Solution:** the LLM generates 3 additional search queries covering different aspects of the topic:

```
Original:      "образование в Казахстане"
Sub-query 1:   "система высшего образования Болонский процесс РК"
Sub-query 2:   "качество школьного образования PISA Казахстан"
Sub-query 3:   "подготовка педагогов реформа образования"
```

Each sub-query retrieves its own set of chunks, which are merged and deduplicated before reranking.

### Cross-Encoder Reranking

The bi-encoder (bge-m3) is fast but imprecise: it compares pre-computed vectors independently. The cross-encoder reads the query and chunk **together**, producing a more accurate relevance score:

| Stage | Model | Speed | Accuracy | Role |
|-------|-------|-------|----------|------|
| Retrieval | bge-m3 (bi-encoder) | Fast (~ms per query) | Moderate | Find candidates |
| Reranking | bge-reranker-v2-m3 (cross-encoder) | Slow (~1.5s per pair) | High | Filter & rank |

### Keyword Supplementary Search

Content words are extracted from the query and used as a `$contains` filter in ChromaDB. This catches relevant chunks that are close in topic but distant in embedding space.

---

## Installation

### Prerequisites

- Python 3.11+
- 4 GB RAM minimum
- LLM API key from [Alem AI](https://llm.alem.ai)

### Setup

```bash
# 1. Clone and create virtual environment
git clone https://github.com/<your-username>/rag-kkson.git
cd rag-kkson
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv/Scripts/activate         # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set your LLM_API_KEY

# 4. Collect articles (automated)
python -m scripts.scrape_articles all --limit 500

# 5. Build vector database
python -m scripts.ingest
# First run downloads bge-m3 model (~2 GB), then caches locally

# 6. Start server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

---

## Data Collection

The scraping system covers **100% of the KKSON journal list** (121 journals) through three methods:

| Method | Journals | Protocol |
|--------|----------|----------|
| OJS journals | 102 | OAI-PMH (standardized) |
| Custom scrapers | 19 | Per-site HTML parsing |
| CyberLeninka | supplementary | OAI-PMH |

### Institutional Coverage

| Institution | Disciplines | Journals |
|-------------|------------|----------|
| Al-Farabi KazNU | Biology, chemistry, math, law, economics, philology, + 15 more | 20 |
| Gumilyov ENU | History, law, economics, pedagogy, biology, CS, + 8 more | 15 |
| NAS RK | Science, physics, social studies, biomedicine, + 4 more | 8 |
| Abai KazNPU | Pedagogy, psychology, history, philology, + 4 more | 8 |
| Buketov KarU | Pedagogy, law, philology, economics, + 3 more | 7 |
| Other (30+ institutions) | Agriculture, engineering, medicine, IT, + more | 63 |

```bash
# Scrape all sources
python -m scripts.scrape_articles all --limit 3000

# Or individually
python -m scripts.scrape_articles cyberleninka --limit 200
python -m scripts.scrape_articles ojs --limit 1500
python -m scripts.scrape_articles nanrk --limit 100
python -m scripts.scrape_articles custom --limit 200
```

---

## Usage

### Web Interface

The web interface supports:

- **Multilingual queries** — Russian, Kazakh, English
- **Streaming answers** — text appears in real-time via SSE
- **Source cards** — file name, page number, relevance score, text preview
- **Search history** — stored locally with bookmarks and export (MD/TXT)
- **Dark/light theme** — toggleable with Ctrl+D
- **UI language** — switchable between RU/KZ/EN
- **Keyboard shortcuts** — Ctrl+Enter (search), Ctrl+K (focus), Ctrl+H (sidebar)

### Example Queries

| Query | Language | Expected Result |
|-------|----------|----------------|
| Закон об арбитраже 2016 года | RU | Specific law with dates and references |
| Қазақстан экономикасы | KZ | Cross-lingual: finds RU/EN articles |
| environmental protection Kazakhstan | EN | Cross-lingual: finds RU articles about ecology |
| квантовая физика чёрных дыр | RU | Honest refusal: topic not in database |

---

## API Reference

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/` | GET | Web interface | HTML |
| `/api/search?q=...&keyword=...` | GET | Search chunks | JSON |
| `/api/answer?q=...&keyword=...` | GET | Streaming answer | SSE |
| `/api/stats` | GET | Collection stats | JSON |

### SSE Event Format (`/api/answer`)

```
event: sources
data: [{"file": "...", "page": 1, "score": 0.85, "text": "..."}]

data: First chunk of answer text...
data: Second chunk...

event: done
data: [DONE]
```

---

## Evaluation Results

Testing was conducted across 5 query types: narrow specific, broad topic, Kazakh language, English language, and out-of-domain.

| # | Query | Language | Sources Found | Result |
|---|-------|----------|---------------|--------|
| 1 | Закон об арбитраже 2016 года | RU | 2 | Accurate: specific dates, law numbers |
| 2 | Образование в Казахстане | RU | 4 | Comprehensive: 4 journals, multiple aspects |
| 3 | Қазақстан экономикасы | KZ | 5 | Cross-lingual: KZ query found RU/EN articles |
| 4 | Environmental protection Kazakhstan | EN | 4 | Cross-lingual: EN query found RU articles |
| 5 | Квантовая физика чёрных дыр | RU | 0 | Correct refusal: no hallucination |

**Key findings:**
- Cross-lingual retrieval works correctly (bge-m3)
- Query expansion improves coverage for broad topics (4-5 diverse sources vs 1-2 without)
- No hallucination on out-of-domain queries
- All assertions backed by source citations

Full test report: [test_results.md](test_results.md)

---

## Project Structure

```
rag-kkson/
├── app/
│   ├── main.py                  # FastAPI app, 4 endpoints, SSE streaming
│   ├── config.py                # Centralized settings from .env
│   ├── ingestion/
│   │   ├── pdf_parser.py        # PDF → text (PyMuPDF)
│   │   ├── chunker.py           # Text → chunks (1500 chars, 150 overlap)
│   │   └── embedder.py          # Chunks → vectors → ChromaDB
│   ├── retrieval/
│   │   ├── search.py            # Semantic, hybrid, multi-query search
│   │   ├── query_expander.py    # LLM-based query expansion
│   │   └── reranker.py          # Cross-encoder reranking
│   ├── generation/
│   │   └── answerer.py          # Qwen 3 streaming generation
│   ├── templates/
│   │   └── index.html           # SPA frontend
│   └── static/
│       ├── css/                 # Themes + layout (1200 lines)
│       └── js/app.js            # App logic, i18n, history (1100 lines)
├── scripts/
│   ├── scrape_articles.py       # Article scraper (121 journals)
│   ├── ingest.py                # CLI ingestion pipeline
│   ├── generate_test_data.py    # Synthetic test PDF generator
│   └── test_search.py           # Search testing CLI
├── tests/
│   ├── test_pipeline.py         # 17 unit tests (PDF, chunking)
│   └── test_search.py           # Embedding & search tests
├── data/
│   ├── pdfs/                    # Article PDFs (not tracked in git)
│   ├── koknvo_full_list.json    # KKSON journal registry
│   └── koknvo_parsed.json       # Parsed journal metadata
├── requirements.txt             # 15 dependencies
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── test_results.md              # Evaluation results
```

**Codebase:** ~3000 lines of Python, ~2300 lines of frontend (HTML + CSS + JS)

---

## Deployment

### Docker (recommended)

```bash
# Build and run
docker compose up -d --build

# Ingest articles
docker compose exec rag python -m scripts.scrape_articles all --limit 500
docker compose exec rag python -m scripts.ingest
```

### VPS Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 5 GB | 10 GB |
| Cost | ~5 EUR/month | ~10 EUR/month |

Tested on: Hetzner CX22 (2 vCPU, 4 GB RAM, ~5 EUR/month)

### Cost Breakdown

| Component | Cost |
|-----------|------|
| VPS (Hetzner CX22) | ~5 EUR/month |
| Embedding model (bge-m3) | Free (runs locally) |
| Vector database (ChromaDB) | Free (serverless) |
| LLM API (Qwen 3 via Alem AI) | Free tier |
| **Total** | **~5 EUR/month** |

---

## Configuration

All settings are configured via environment variables (`.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_KEY` | — | Alem AI API key (required) |
| `LLM_BASE_URL` | `https://llm.alem.ai/v1` | LLM API endpoint |
| `LLM_MODEL` | `qwen3` | Model name |
| `EMBEDDING_DEVICE` | `cpu` | `cpu` or `cuda` |
| `RERANKER_ENABLED` | `true` | Enable cross-encoder reranking |
| `RERANKER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `QUERY_EXPANSION` | `true` | Enable multi-query expansion |

---

## Testing

```bash
# Unit tests (PDF parsing, chunking) — 17 tests, ~1 sec
python -m pytest tests/test_pipeline.py -v

# Full tests (includes embeddings, requires model download) — ~30 sec
python -m pytest tests/ -v
```

---

## License

This project was developed as part of academic research at [your university].

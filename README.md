# PaperTrail AI

A small, local research assistant for arXiv papers. Import a paper, let the app process it,
then ask questions about it. Every answer cites the exact passages it is based on, and the
app says so when the imported papers do not contain enough evidence.

Built as a compact full-stack portfolio project covering data engineering (ingestion,
validation, idempotency, document processing, migrations) and AI engineering (embeddings,
vector search, retrieval-augmented generation, citations, abstention). Everything runs on
your own machine and costs nothing: no paid API and no cloud service.

## What it does

1. **Import** a paper by arXiv ID: metadata and authors are fetched, validated and stored.
2. **Process** it: the PDF is downloaded, text is extracted and split into overlapping passages.
3. **Index** it: each passage gets an embedding vector, stored in PostgreSQL with pgvector.
4. **Search** by meaning: find the passages closest to a query.
5. **Ask** a question: the best passages are given to a language model, which answers only from
   them. The answer's `[1]`, `[2]` markers open the exact stored source passages.
6. **Abstain**: if nothing relevant is found, the app says so instead of guessing.

## Architecture

```text
arXiv
 ↓
ingestion  (validate ID → fetch → normalize → validate fields → idempotent store)
 ↓
PostgreSQL  (papers, authors, paper_authors, ingestion_runs, passages)
 ↓
PDF extraction  (pypdf, in memory; scanned PDFs rejected)
 ↓
chunking  (150-word windows, 30-word overlap, deterministic)
 ↓
embeddings  (bge-small-en-v1.5, local ONNX, 384 dimensions)
 ↓
pgvector  (passages.embedding, cosine similarity)
 ↓
semantic retrieval  (top-k passages)
 ↓
RAG  (similarity threshold → grounded prompt → local LLM → citation check)
 ↓
FastAPI
 ↓
React
```

PostgreSQL is the only database; vectors live in the same row as the passage they describe.

## Technologies, and why

| Technology | Why it is used here |
|---|---|
| **Python 3.13, FastAPI** | Typed request/response models, automatic validation and API docs (`/docs`). |
| **PostgreSQL 17 + pgvector** | One database for relational data *and* vectors; a result row is directly citable (text, page, paper). Exact search over a few thousand passages takes about a millisecond. |
| **SQLAlchemy 2 + Alembic** | ORM for the models; versioned, reversible migrations, with a test that fails if models and migrations drift apart. |
| **pypdf** | Small, pure-Python text extraction. No OCR by design. |
| **ONNX Runtime + `tokenizers`** | Runs the embedding model locally on the CPU without PyTorch (about 125 MB instead of several GB). |
| **BAAI/bge-small-en-v1.5** | Small (about 64 MB quantized), MIT-licensed, strong for English text; 384-dimension vectors. |
| **Ollama + qwen2.5:7b** | Free, offline answer generation. The model sits behind a two-method interface, so a hosted model would be a single new class. |
| **React 19 + TypeScript + Vite** | A small typed UI; the Vite dev server proxies `/api` to the backend, so no CORS setup is needed. |
| **Vitest, Testing Library, Playwright** | Many fast component tests with a mocked backend, plus a few end-to-end tests on the real stack. |
| **Docker Compose** | One command starts PostgreSQL with pgvector. |
| **ruff, mypy (strict), oxlint, tsc** | Formatting, linting and static typing for both halves. |

## Running locally

**Prerequisites:** Docker Desktop, Python 3.12+, Node.js 20+ (built with 3.13 and 24), and
[Ollama](https://ollama.com) for generated answers (optional: search works without it).

```bash
# 1. Configuration
cp .env.example .env

# 2. Database: PostgreSQL + pgvector on localhost:5433
docker compose up -d

# 3. Embedding model (one time, about 64 MB, MIT license): see "Embedding model" below

# 4. Language model (one time, about 4.7 GB, Apache-2.0)
ollama pull qwen2.5:7b
#    then set LLM_PROVIDER=ollama in .env

# 5. Backend (http://localhost:8001, API docs at /docs)
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8001

# 6. Frontend, in a second terminal (http://localhost:5173)
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Stop the database with `docker compose down` (add `-v` to delete
its data).

### Embedding model

The embedding model files are not stored in git. Create `models/bge-small-en-v1.5/` in the
repository root (or point `EMBEDDING_MODEL_DIR` elsewhere) and put these files in it, taken
from the Hugging Face repository
[`Qdrant/bge-small-en-v1.5-onnx-Q`](https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q)
(MIT license; an ONNX export of BAAI/bge-small-en-v1.5):

- `model_optimized.onnx` (about 64 MB)
- `tokenizer.json`

If the files are missing, `POST /papers/{id}/index`, `/search` and `/ask` return a clear 503
that says so.

### Configuration

All settings are environment variables, read from `.env` in the repository root. Defaults
are in [.env.example](.env.example) and [backend/app/core/config.py](backend/app/core/config.py).

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_*` | `papertrail` / `localhost:5433` | Database connection (also used by `docker-compose.yml`) |
| `LLM_PROVIDER` | `none` | `none` or `ollama`. With `none`, `/ask` can still abstain but returns 503 when an answer is needed |
| `OLLAMA_URL`, `OLLAMA_MODEL` | `http://localhost:11434`, `qwen2.5:7b` | Local model server |
| `RAG_MIN_SCORE` | `0.70` | Minimum cosine similarity for a passage to count as evidence |
| `CHUNK_SIZE_WORDS`, `CHUNK_OVERLAP_WORDS` | `150`, `30` | Chunking (overlap must be smaller than size) |
| `EMBEDDING_MODEL_DIR` | `models/bge-small-en-v1.5` | Where the embedding model files are |
| `LOG_LEVEL` | `INFO` | Backend log level |

## Example workflow

In the UI: **Papers** → type `1706.03762` → **Import paper** → **Process & index** → **Ask** →
*"How are positional encodings computed in the Transformer?"* → click the `[1]` in the answer
to read the exact passage it came from. Then ask *"What is a good recipe for sourdough bread?"*
and see the app abstain.

The same workflow from the command line, against a running backend (it checks that every
citation is the exact text of a stored passage and that an unrelated question abstains):

```bash
python3 scripts/smoke_test.py
```

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/info` | Non-secret configuration (models, threshold, chunking) |
| GET | `/papers?limit=50&offset=0` | Papers, newest first, with authors, status and passage count |
| GET | `/papers/{paper_id}` | One paper with abstract (404 if missing) |
| POST | `/papers/import` | `{"arxiv_id": "1706.03762"}`. 201 created, 200 already imported (idempotent), 422 invalid ID, 404 not on arXiv, 502/503 arXiv problems. A 429 from arXiv is retried once |
| POST | `/papers/{paper_id}/process` | Download the PDF, extract text, rebuild passages. Safe to repeat. 422 if the PDF is unusable, 502/503 download problems |
| GET | `/papers/{paper_id}/passages` | The paper's passages in order |
| POST | `/papers/{paper_id}/index` | Embed every passage and store the vectors. Safe to repeat. 409 if not processed yet |
| POST | `/search` | `{"query": "...", "limit": 5, "paper_ids": []}` → passages with cosine-similarity scores |
| POST | `/ask` | `{"question": "...", "paper_ids": [], "top_k": 5}` → `answer`, `abstained`, `abstention_reason`, `citations`, `best_score` |

Errors are always JSON `{"detail": "..."}` with a readable message; stack traces only go to the
server log.

## Database schema

```text
papers ──< paper_authors >── authors          papers ──< passages
   id, arxiv_id (unique), title, abstract,       id, paper_id, position (unique per paper),
   published_date, source_url, pdf_url,          text, page, section (unused), embedding
   ingestion_status, processing_error,           vector(384)
   created_at, updated_at                     ingestion_runs: requested_arxiv_id, status,
                                                 started_at, completed_at, error_message
```

`ingestion_status` moves `imported → processed → indexed` (or `failed`, keeping the reason).
Reprocessing a paper replaces its passages, which removes their embeddings, so it must be
indexed again.

## How retrieval and answering work

- **Chunking:** a sliding window over the paper's words (150 words, step 120), remembering the
  page each chunk starts on. The same PDF and settings always give the same passages.
- **Search:** `score = 1 - (embedding <=> query)`, i.e. cosine similarity, computed by pgvector.
  Exact scan, no approximate index (not needed at this size).
- **Answering:** the top passages scoring at least `RAG_MIN_SCORE` are numbered `[1]..[n]` in the
  prompt. The model must answer only from them, cite every statement, write plain text, and
  reply `INSUFFICIENT_EVIDENCE` otherwise. Citation markers are parsed in code; numbers that do
  not match a provided passage are removed, so every citation maps to a real stored passage.
- **Abstention** (`abstention_reason`):

  | Reason | When |
  |---|---|
  | `no_relevant_passages` | No passage scored ≥ `RAG_MIN_SCORE`. The language model is not called. |
  | `model_insufficient_evidence` | The model replied `INSUFFICIENT_EVIDENCE`. |
  | `no_valid_citations` | The answer cited none of the provided passages, so it is treated as ungrounded. |

  The 0.70 threshold is a heuristic: on the two test papers, answerable questions scored 0.73–0.84
  and unanswerable ones 0.47–0.70. The margin is thin and it is not a guarantee.

## Testing

Backend, from `backend/` (needs `docker compose up -d`; tests use a separate
`papertrail_test` database, migrated with Alembic and rolled back per test, so development
data is never touched):

```bash
.venv/bin/ruff format --check .   # formatting
.venv/bin/ruff check .            # lint
.venv/bin/mypy app tests          # static typing (strict)
.venv/bin/pytest                  # all tests; no network, no model download
.venv/bin/pytest -m model         # opt-in: loads the real embedding model
.venv/bin/pytest -m live          # opt-in: one real request to arXiv
```

Frontend, from `frontend/`:

```bash
npm run lint                      # oxlint
npm run typecheck                 # TypeScript
npm test                          # Vitest + Testing Library (mocked backend)
npm run build                     # production build
npm run e2e                       # Playwright on the real stack (Postgres, backend, Ollama; uses installed Chrome)
```

Integration, against a running backend: `python3 scripts/smoke_test.py`.

## Project layout

```text
papertrail-ai/
├── backend/
│   ├── app/
│   │   ├── api/        # HTTP routes, dependencies, error mapping
│   │   ├── core/       # settings
│   │   ├── db/         # engine, sessions, declarative base
│   │   ├── models/     # SQLAlchemy models
│   │   ├── schemas/    # Pydantic request/response models
│   │   ├── services/   # arXiv, ingestion, PDF, chunking, embeddings, indexing, search, RAG, LLM
│   │   └── main.py
│   ├── alembic/        # migrations
│   ├── tests/
│   └── pyproject.toml
├── frontend/           # React + TypeScript (src/, e2e/)
├── scripts/smoke_test.py
├── docker-compose.yml
├── .env.example
└── README.md
```

## Limitations

These are intentional scope choices, not oversights.

- **Local and single-user.** No authentication, no multi-tenancy, no production deployment. The
  API has no access control, so run it on localhost only. The development database password is
  `papertrail`, and the database port is bound to localhost.
- **arXiv only.** No other sources and no entity resolution: authors are matched by exact name, so
  two different people with the same name share one row.
- **PDF extraction is imperfect.** There is no OCR (scanned PDFs are rejected) and no layout
  analysis, so headers, author emails, figure labels and equations appear as noise in passages,
  and a real hyphen at a line break can be joined into one word ("Englishto-German").
- **Semantic retrieval only.** No keyword or hybrid search and no reranking, so a passage of
  figure labels can outrank the real explanation.
- **Simple RAG.** One retrieval step, no agents and no multi-step reasoning. Answer quality is that
  of a small local model, and prompt-injection text inside a PDF is only mitigated by instructions,
  not prevented.
- **Simple abstention.** A fixed similarity threshold, a model signal and a citation rule; no
  verifier. Weak or borderline evidence can slip through, and some answerable questions may
  abstain.
- **Slow answers.** Generating an answer with the local model takes roughly 5–20 seconds.
- **Reproducibility.** The frontend has a lockfile; Python dependencies have lower bounds only.
  The embedding model files are fetched manually.
- **Exact vector search**, not approximate: fine for thousands of passages, not for millions.

# Architecture

A short map of how PaperTrail AI is put together. For setup and usage see the [README](../README.md).

## Components

```text
Browser ── React + TypeScript (Vite dev server, proxies /api/*) ──┐
                                                                    ▼
                                                    FastAPI (backend/app/api)
                                                                    │
                      ┌─────────────────────────────┬───────────────┴──────────────┐
                      ▼                             ▼                              ▼
          arXiv API / PDF download        PostgreSQL + pgvector          Local models (CPU)
          (httpx, one 429 retry)          papers, authors, passages,     bge-small-en-v1.5 (ONNX Runtime)
                                          ingestion_runs                 qwen2.5:7b (Ollama, HTTP)
```

## Backend layout

| Package | Responsibility |
|---|---|
| `api/` | HTTP routes, request validation, mapping of known failures to HTTP statuses, dependency wiring (`deps.py`) |
| `services/` | All business logic. One module per concern: `arxiv`, `ingestion`, `pdf`, `chunking`, `processing`, `embeddings`, `indexing`, `search`, `rag`, `llm`, `ollama` |
| `models/` | SQLAlchemy ORM models |
| `schemas/` | Pydantic request/response shapes (kept separate from ORM models so the API does not change when tables do) |
| `db/` | Engine, session factory, declarative base |
| `core/` | Settings (environment variables / `.env`) |
| `alembic/` | Migrations |

Routes stay thin; services take their collaborators (database session, arXiv client, PDF downloader,
embedder, LLM) as arguments. That is what lets the automated tests replace every external dependency
with a fake.

## Data model

```text
papers ──< paper_authors >── authors            papers ──< passages
 id, arxiv_id (unique), title, abstract,         id, paper_id, position (unique per paper), text,
 published_date, source_url, pdf_url,            page, section (reserved, currently unused),
 ingestion_status, processing_error,             embedding vector(384)
 created_at, updated_at
                                                ingestion_runs: requested_arxiv_id, status,
                                                 started_at, completed_at, error_message
```

- `ingestion_status` moves `imported → processed → indexed`, or `failed` with the reason in `processing_error`.
- The unique `arxiv_id`, the unique author name, and the `(paper_id, position)` constraint are what make
  imports and reprocessing safe even under concurrent requests.
- Deleting a paper cascades to its passages and author links; authors are kept.
- `ingestion_runs` records every import attempt, including failed ones, and has no foreign key to `papers`
  because a failed attempt may have no paper.

## Flows

**Import** (`POST /papers/import`): normalize the ID (drops the version suffix, accepts `arXiv:` prefix) →
if already stored, return it without calling arXiv → fetch the Atom feed → parse and validate (title, abstract,
date, at least one author) → store authors with `INSERT … ON CONFLICT DO NOTHING`, then the paper and links
→ mark the ingestion run succeeded. Any failure rolls back partial data and records the reason.

**Process** (`POST /papers/{id}/process`): download the PDF into memory (size-capped, must start with
`%PDF-`) → extract text per page with pypdf → clean (Unicode normalization, hyphen re-joining, control
characters) → slide a 150-word window with 30 words of overlap, remembering each chunk's starting page →
in one transaction, lock the paper row, delete its old passages and insert the new ones. If processing
fails, earlier good passages are kept.

**Index** (`POST /papers/{id}/index`): embed all passages in batches, check the result has shape
`(passages, 384)`, write the vectors and set the status to `indexed` in one transaction.

**Search** (`POST /search`): embed the query with bge's query prefix, then one SQL query ordered by
`embedding <=> query` (cosine distance), with `score = 1 − distance`. Exact scan; ties broken by passage ID.

**Ask** (`POST /ask`): search → keep passages with score ≥ `RAG_MIN_SCORE` → (none left: abstain, model not
called) → build a prompt with numbered passages `[1]..[n]` → model reply → abstain if it says
`INSUFFICIENT_EVIDENCE` → parse `[n]` markers, dropping numbers that do not match a provided passage →
abstain if no valid citation remains → return the answer with each citation's stored passage.

## Error handling

Each service raises its own exception type with a message that is safe to show. The API layer maps them
to statuses (422 invalid input, 404 not found, 409 wrong state, 502/503 upstream or model unavailable,
500 database). Stack traces go to the server log only. Two global handlers return JSON for unexpected
database errors (503) and bugs (500), so the frontend never receives a plain-text error page.

## Testing strategy

- **Unit and API tests (pytest):** a real PostgreSQL test database (migrated with Alembic, rolled back per
  test), with fakes for arXiv, the PDF server, the embedder and the LLM. No network, no model.
- **Opt-in tests:** `-m model` runs the real embedding model; `-m live` makes one real arXiv request.
- **Frontend (Vitest):** components and pages with a mocked `fetch`.
- **End to end:** Playwright against the real stack, and `scripts/smoke_test.py` against a running backend.

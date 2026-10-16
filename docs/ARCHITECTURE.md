# Architecture

## Layout

```text
backend/app/
  api/        routes, dependency wiring, error-to-status mapping
  services/   arxiv, ingestion, pdf, chunking, processing, embeddings, indexing, search, rag, llm, ollama
  models/     SQLAlchemy models
  schemas/    Pydantic request/response models
  db/         engine and sessions
  core/       settings
frontend/src/ pages (Papers, PaperDetail, Ask, About) and components
```

Routes are thin. Services get their dependencies (DB session, arXiv client, PDF downloader, embedder,
LLM) passed in, which is what lets the tests swap them for fakes.

## Data model

```text
papers ──< paper_authors >── authors
papers ──< passages (position unique per paper, embedding vector(384))
ingestion_runs (one row per import attempt, including failures)
```

`papers.ingestion_status` goes `imported → processed → indexed`, or `failed` with the reason stored in
`processing_error`.

## Flows

- **Import:** normalize the arXiv ID. If the paper already exists, return it. Otherwise fetch the Atom
  feed, validate it, and insert authors (`ON CONFLICT DO NOTHING`), the paper and the author links in
  one transaction. A 429 from arXiv is retried once.
- **Process:** download the PDF into memory, extract and clean the text per page, cut it into
  150-word windows with 30 words of overlap, then replace the paper's passages in one transaction
  (with the paper row locked). If it fails, the old passages are kept.
- **Index:** embed all passages, check the shape is `(n, 384)`, and store the vectors.
- **Search:** one SQL query ordered by `embedding <=> query` (cosine distance), with
  `score = 1 - distance`.
- **Ask:** search, then keep passages with score ≥ 0.70. If none are left, abstain. Otherwise prompt
  the LLM with numbered passages, parse the `[n]` markers, and drop any that don't match. Abstain if
  the model says `INSUFFICIENT_EVIDENCE` or no valid citation is left.

## Errors

Each service raises its own exception type. The API maps them to 404, 409, 422, 502, 503 or 500 with
a short JSON message. Unexpected errors get a generic JSON 500 (503 for database errors), and stack
traces only go to the log.

## Tests

- **pytest:** runs against a real test database that is rolled back after each test, with fakes for
  arXiv, PDFs, the embedder and the LLM.
- **Opt-in suites:** `-m model` uses the real embedding model and `-m live` makes one real arXiv request.
- **Vitest:** covers the frontend with a mocked `fetch`.
- **Playwright and `scripts/smoke_test.py`:** run against the real stack.

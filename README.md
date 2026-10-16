# PaperTrail AI

A local research assistant for arXiv papers. You import a paper, it gets split into passages and
embedded, and then you can ask questions. Answers cite the passages they come from, and if nothing
relevant is found it says so instead of guessing.

Runs entirely on your machine: PostgreSQL + pgvector, a local embedding model, and a local LLM
through Ollama. No paid APIs.

![Ask page with an answer and the cited passage](docs/images/ask-citation.png)

## How it works

```text
arXiv → import → PostgreSQL → PDF text → chunks → embeddings (pgvector)
      → search → RAG with a local LLM → answer with citations → FastAPI → React
```

- **Import:** fetches metadata from the arXiv API. Importing the same paper twice is a no-op.
- **Process:** downloads the PDF, extracts the text with pypdf, and splits it into 150-word chunks
  with 30 words of overlap.
- **Index:** embeds each chunk with `bge-small-en-v1.5` (384 dims) and stores it in a pgvector column.
- **Ask:** retrieves the most similar chunks (cosine similarity). Chunks scoring at least 0.70 go to
  `qwen2.5:7b`, which must answer only from them and cite them as `[1]`, `[2]`. If nothing passes
  the threshold, the model says the evidence is insufficient, or the answer cites nothing valid,
  the app abstains.

I used pgvector instead of a separate vector database because the corpus is small, and keeping
vectors next to the passage text makes every result directly citable. More detail is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Stack:** Python 3.13, FastAPI, SQLAlchemy, Alembic, PostgreSQL 17, pgvector, pypdf, ONNX Runtime,
Ollama, React 19, TypeScript, Vite, pytest, Vitest, Playwright, Docker Compose.

## Screenshots

| Papers | Answer | Abstention |
|---|---|---|
| ![Papers](docs/images/papers.png) | ![Answer](docs/images/ask-answer.png) | ![Abstention](docs/images/ask-abstain.png) |

## Running it

You need Docker, Python 3.12+, Node 20+ and [Ollama](https://ollama.com). The repo doesn't install
Ollama or download any models for you.

```bash
cp .env.example .env
docker compose up -d                 # PostgreSQL + pgvector on localhost:5433
```

Embedding model (about 64 MB, MIT), from
[Qdrant/bge-small-en-v1.5-onnx-Q](https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q):

```bash
mkdir -p models/bge-small-en-v1.5
curl -L -o models/bge-small-en-v1.5/model_optimized.onnx \
  https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/main/model_optimized.onnx
curl -L -o models/bge-small-en-v1.5/tokenizer.json \
  https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/main/tokenizer.json
```

LLM (about 4.7 GB, Apache-2.0): `ollama pull qwen2.5:7b`, then set `LLM_PROVIDER=ollama` in `.env`.
Without it, search still works but `/ask` returns 503 when it needs to generate an answer.

Backend:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8001
```

Frontend:

```bash
cd frontend
npm ci
npm run dev                          # http://localhost:5173
```

Then import `1706.03762` on the Papers page, click **Process & index**, and ask something on the Ask page.
All settings are in [.env.example](.env.example).

## Tests

```bash
cd backend
.venv/bin/ruff check . && .venv/bin/mypy app tests
.venv/bin/pytest                     # needs PostgreSQL; fakes replace arXiv, PDFs, embedder and LLM
.venv/bin/pytest -m model            # real embedding model
.venv/bin/pytest -m live             # one real arXiv request

cd ../frontend
npm run lint && npm run typecheck && npm test && npm run build
npm run e2e                          # Playwright against the real stack (needs Ollama and Chrome)

python3 scripts/smoke_test.py        # end-to-end check against a running backend
```

## Some decisions

- **Exact search, no HNSW index:** with a few thousand passages a full scan takes about a millisecond.
- **Fixed-size chunks:** deterministic, so re-processing gives the same passages.
- **Process and index are separate steps:** a paper can be re-embedded without downloading the PDF again.
- **Local models:** free to run, no API keys. The LLM is behind a small interface, so swapping
  providers means writing one class.
- **Fakes in tests:** the test suite is fast and doesn't need models or network access.
- **Citations are checked in code:** `[n]` markers that don't match a retrieved passage are dropped.

## Evaluation

I ran 12 questions against 5 papers. Retrieval found the right paper for 8 of 9 answerable
questions, and all 3 unrelated questions abstained. One answerable question was missed because
retrieval returned the wrong paper. Two answers included details their citation didn't support.
The 0.70 threshold worked on this set, but the margin was only about 0.06. It's a small sanity
check, not a benchmark. Details: [docs/MANUAL_EVALUATION.md](docs/MANUAL_EVALUATION.md).

## Limitations

- Local and single-user, no authentication, not deployed.
- arXiv only. Authors are matched by exact name.
- No OCR, and PDF extraction is noisy (headers, figure labels, equations).
- Semantic search only, no hybrid search or reranking.
- The 0.70 threshold is a heuristic tested on a small sample.
- Citations are checked to exist, not to support the claim.
- Answers take about 10 seconds with the local model.
- Python dependencies aren't pinned.

## License

MIT, see [LICENSE](LICENSE). The models aren't part of this repo and keep their own licenses
(bge-small-en-v1.5: MIT, qwen2.5: Apache-2.0).

import { api } from '../api'
import { ErrorMessage } from '../components/ErrorMessage'
import { useLoad } from '../useLoad'

export function AboutPage() {
  const health = useLoad(api.health)
  const info = useLoad(api.info)

  return (
    <>
      <h1>About PaperTrail AI</h1>
      <p>
        PaperTrail imports scientific papers from arXiv and answers questions about them. Every
        answer cites the exact passages it is based on, and the app says so when the imported
        papers don't contain enough evidence.
      </p>

      <section className="card" aria-labelledby="architecture-heading">
        <h2 id="architecture-heading">How it works</h2>
        <ol>
          <li>Import: paper metadata is fetched from the arXiv API and stored in PostgreSQL.</li>
          <li>Process: the PDF's text is extracted and split into overlapping passages.</li>
          <li>Index: each passage is turned into an embedding vector stored with pgvector.</li>
          <li>Ask: the most similar passages are retrieved and a language model answers from them, citing each source.</li>
        </ol>
        <p className="muted">FastAPI · PostgreSQL + pgvector · React + TypeScript</p>
      </section>

      <section className="card" aria-labelledby="status-heading">
        <h2 id="status-heading">System status</h2>
        {health.loading && <p className="muted">Checking backend…</p>}
        {health.error && <ErrorMessage message={`Backend: ${health.error}`} />}
        {health.data && (
          <p>
            Backend: <strong>{health.data.status === 'ok' ? 'OK' : health.data.status}</strong>
          </p>
        )}
        {info.data && (
          <dl className="facts">
            <div>
              <dt>Embedding model</dt>
              <dd>
                {info.data.embedding_model} ({info.data.embedding_dimension} dimensions)
              </dd>
            </div>
            <div>
              <dt>Language model</dt>
              <dd>
                {info.data.llm_model
                  ? `${info.data.llm_model} via ${info.data.llm_provider}`
                  : 'Not configured (answers disabled)'}
              </dd>
            </div>
            <div>
              <dt>Evidence threshold</dt>
              <dd>similarity ≥ {info.data.rag_min_score.toFixed(2)}</dd>
            </div>
            <div>
              <dt>Chunking</dt>
              <dd>
                {info.data.chunk_size_words} words, {info.data.chunk_overlap_words} overlap
              </dd>
            </div>
          </dl>
        )}
      </section>
    </>
  )
}

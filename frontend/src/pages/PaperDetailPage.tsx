import { useCallback } from 'react'
import { Link, useParams } from 'react-router'
import { api } from '../api'
import { ErrorMessage } from '../components/ErrorMessage'
import { PaperActions } from '../components/PaperActions'
import { StatusBadge } from '../components/StatusBadge'
import { formatDate } from '../format'
import { useLoad } from '../useLoad'

export function PaperDetailPage() {
  const paperId = Number(useParams().paperId)
  const loadPaper = useCallback(() => api.getPaper(paperId), [paperId])
  const loadPassages = useCallback(() => api.listPassages(paperId), [paperId])
  const paper = useLoad(loadPaper)
  const passages = useLoad(loadPassages)

  const refresh = () => {
    paper.reload()
    passages.reload()
  }

  if (paper.error) return <ErrorMessage message={paper.error} />
  if (!paper.data) return <p className="muted">Loading paper…</p>
  const p = paper.data

  return (
    <article>
      <p>
        <Link to="/">← All papers</Link>
      </p>
      <h1>{p.title}</h1>
      <p className="muted">{p.authors.map((author) => author.name).join(', ')}</p>

      <dl className="facts card">
        <div>
          <dt>Published</dt>
          <dd>{formatDate(p.published_date)}</dd>
        </div>
        <div>
          <dt>arXiv</dt>
          <dd>
            <a href={p.source_url} target="_blank" rel="noreferrer">
              {p.arxiv_id}
            </a>{' '}
            ·{' '}
            <a href={p.pdf_url} target="_blank" rel="noreferrer">
              PDF
            </a>
          </dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            <StatusBadge status={p.ingestion_status} />
          </dd>
        </div>
        <div>
          <dt>Passages</dt>
          <dd>{p.passage_count}</dd>
        </div>
      </dl>

      {p.processing_error && <ErrorMessage message={`Last error: ${p.processing_error}`} />}
      <PaperActions paperId={p.id} status={p.ingestion_status} onChanged={refresh} allowRerun />

      <section aria-labelledby="abstract-heading">
        <h2 id="abstract-heading">Abstract</h2>
        <p>{p.abstract}</p>
      </section>

      <section aria-labelledby="passages-heading" aria-busy={passages.loading}>
        <h2 id="passages-heading">Passages</h2>
        {passages.error && <ErrorMessage message={passages.error} />}
        {passages.data?.length === 0 && (
          <p className="muted">No passages yet. Process the paper to extract its text.</p>
        )}
        <ol className="passage-list">
          {passages.data?.map((passage) => (
            <li key={passage.id} className="card">
              <p className="muted">
                Passage {passage.position + 1}
                {passage.page !== null && ` · page ${passage.page}`}
              </p>
              <p>{passage.text}</p>
            </li>
          ))}
        </ol>
      </section>
    </article>
  )
}

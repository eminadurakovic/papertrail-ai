import { Link } from 'react-router'
import { api } from '../api'
import { ErrorMessage } from '../components/ErrorMessage'
import { ImportForm } from '../components/ImportForm'
import { PaperActions } from '../components/PaperActions'
import { StatusBadge } from '../components/StatusBadge'
import { formatAuthors, formatDate } from '../format'
import { useLoad } from '../useLoad'

export function PapersPage() {
  const { data: papers, error, loading, reload } = useLoad(api.listPapers)

  return (
    <>
      <h1>Papers</h1>
      <section className="card" aria-labelledby="import-heading">
        <h2 id="import-heading">Import a paper from arXiv</h2>
        <ImportForm onImported={reload} />
      </section>

      <section aria-labelledby="library-heading" aria-busy={loading}>
        <h2 id="library-heading">Your library</h2>
        {error && <ErrorMessage message={error} />}
        {loading && !papers && <p className="muted">Loading papers…</p>}
        {papers && papers.length === 0 && (
          <p className="muted">No papers yet. Import one above to get started.</p>
        )}
        {papers && papers.length > 0 && (
          <ul className="paper-list">
            {papers.map((paper) => (
              <li key={paper.id} className="card paper-card">
                <div className="paper-card-main">
                  <h3>
                    <Link to={`/papers/${paper.id}`}>{paper.title}</Link>
                  </h3>
                  <p className="muted">{formatAuthors(paper.authors)}</p>
                  <dl className="facts">
                    <div>
                      <dt>Published</dt>
                      <dd>{formatDate(paper.published_date)}</dd>
                    </div>
                    <div>
                      <dt>arXiv</dt>
                      <dd>{paper.arxiv_id}</dd>
                    </div>
                    <div>
                      <dt>Passages</dt>
                      <dd>{paper.passage_count}</dd>
                    </div>
                    <div>
                      <dt>Status</dt>
                      <dd>
                        <StatusBadge status={paper.ingestion_status} />
                      </dd>
                    </div>
                  </dl>
                </div>
                <PaperActions
                  paperId={paper.id}
                  status={paper.ingestion_status}
                  onChanged={reload}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

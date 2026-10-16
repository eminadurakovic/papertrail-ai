import { useState, type FormEvent } from 'react'
import { api, messageOf } from '../api'
import { AnswerText } from '../components/AnswerText'
import { CitationPanel } from '../components/CitationPanel'
import { ErrorMessage } from '../components/ErrorMessage'
import type { AbstentionReason, AskResponse, Citation } from '../types'
import { useLoad } from '../useLoad'

const ABSTENTION_EXPLANATIONS: Record<AbstentionReason, string> = {
  no_relevant_passages: 'No passage in the indexed papers was similar enough to the question.',
  model_insufficient_evidence: 'The retrieved passages did not contain enough information.',
  no_valid_citations: 'The generated answer did not cite any of the retrieved passages.',
}

export function AskPage() {
  const papers = useLoad(api.listPapers)
  const indexedPapers = (papers.data ?? []).filter((p) => p.ingestion_status === 'indexed')

  const [question, setQuestion] = useState('')
  const [paperId, setPaperId] = useState('') // '' = all indexed papers
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AskResponse | null>(null)
  const [openCitation, setOpenCitation] = useState<Citation | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!question.trim()) return
    setBusy(true)
    setError(null)
    setResult(null)
    setOpenCitation(null)
    try {
      setResult(await api.ask(question.trim(), paperId ? [Number(paperId)] : []))
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={openCitation ? 'with-panel' : undefined}>
      <div>
        <h1>Ask</h1>
        <form className="card ask-form" onSubmit={handleSubmit}>
          <label htmlFor="question">Question</label>
          <textarea
            id="question"
            rows={3}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="e.g. How are positional encodings computed?"
            maxLength={1000}
            disabled={busy}
          />
          <label htmlFor="paper-filter">Search in</label>
          <select
            id="paper-filter"
            value={paperId}
            onChange={(event) => setPaperId(event.target.value)}
            disabled={busy}
          >
            <option value="">All indexed papers</option>
            {indexedPapers.map((paper) => (
              <option key={paper.id} value={paper.id}>
                {paper.title}
              </option>
            ))}
          </select>
          <button type="submit" disabled={busy || !question.trim()}>
            {busy ? 'Searching and answering…' : 'Ask'}
          </button>
          {busy && (
            <p role="status" className="muted">
              Generating an answer with the local model can take 5–20 seconds.
            </p>
          )}
        </form>

        {error && <ErrorMessage message={error} />}

        {result?.abstained && (
          <section className="card abstained" role="status" aria-labelledby="result-heading">
            <h2 id="result-heading">Not enough evidence</h2>
            <p>{result.answer}</p>
            {result.abstention_reason && (
              <p className="muted">
                {ABSTENTION_EXPLANATIONS[result.abstention_reason]}
                {result.best_score !== null &&
                  ` Best similarity found: ${result.best_score.toFixed(2)}.`}
              </p>
            )}
          </section>
        )}

        {result && !result.abstained && (
          <section className="card" aria-labelledby="result-heading">
            <h2 id="result-heading">Answer</h2>
            <AnswerText
              answer={result.answer}
              citations={result.citations}
              onCite={setOpenCitation}
            />
            <h3>Sources</h3>
            <ol className="source-list">
              {result.citations.map((citation) => (
                <li key={citation.number}>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => setOpenCitation(citation)}
                  >
                    [{citation.number}] {citation.paper_title}
                    {citation.page !== null && `, page ${citation.page}`}
                  </button>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>

      {openCitation && (
        <CitationPanel citation={openCitation} onClose={() => setOpenCitation(null)} />
      )}
    </div>
  )
}

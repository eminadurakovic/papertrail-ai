import { useState, type FormEvent } from 'react'
import { api, messageOf } from '../api'
import { ErrorMessage } from './ErrorMessage'

interface Props {
  onImported: () => void
}

export function ImportForm({ onImported }: Props) {
  const [arxivId, setArxivId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const id = arxivId.trim()
    if (!id) {
      setError('Enter an arXiv ID, for example 1706.03762.')
      return
    }
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const { created, paper } = await api.importPaper(id)
      setNotice(
        created ? `Imported “${paper.title}”.` : `“${paper.title}” was already imported.`,
      )
      setArxivId('')
      onImported()
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="import-form" onSubmit={handleSubmit} noValidate>
      <label htmlFor="arxiv-id">arXiv ID</label>
      <div className="row">
        <input
          id="arxiv-id"
          value={arxivId}
          onChange={(event) => setArxivId(event.target.value)}
          placeholder="e.g. 1706.03762"
          autoComplete="off"
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          {busy ? 'Importing…' : 'Import paper'}
        </button>
      </div>
      {error && <ErrorMessage message={error} />}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
    </form>
  )
}

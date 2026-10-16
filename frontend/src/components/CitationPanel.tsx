import { useEffect, useRef } from 'react'
import { Link } from 'react-router'
import type { Citation } from '../types'

interface Props {
  citation: Citation
  onClose: () => void
}

/** Side panel showing the exact stored passage behind a citation. */
export function CitationPanel({ citation, onClose }: Props) {
  const closeButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeButton.current?.focus() // move keyboard focus into the panel
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [citation, onClose])

  return (
    <aside className="citation-panel" role="dialog" aria-labelledby="citation-title">
      <div className="citation-panel-header">
        <h2 id="citation-title">Source [{citation.number}]</h2>
        <button ref={closeButton} type="button" className="secondary" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="citation-paper">
        <Link to={`/papers/${citation.paper_id}`}>{citation.paper_title}</Link>
      </p>
      <p className="muted">
        {citation.page !== null && `Page ${citation.page} · `}
        Passage {citation.position + 1} · similarity {citation.score.toFixed(2)}
      </p>
      <blockquote>{citation.passage_text}</blockquote>
    </aside>
  )
}

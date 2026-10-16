import type { Citation } from '../types'

interface Props {
  answer: string
  citations: Citation[]
  onCite: (citation: Citation) => void
}

/** Renders the answer, turning each [n] marker into a button that opens that source. */
export function AnswerText({ answer, citations, onCite }: Props) {
  const byNumber = new Map(citations.map((citation) => [citation.number, citation]))
  // split() with a capture group keeps the numbers: "a [1] b" -> ["a ", "1", " b"]
  const parts = answer.split(/\[(\d+)\]/)

  return (
    <p className="answer-text">
      {parts.map((part, index) => {
        const citation = index % 2 === 1 ? byNumber.get(Number(part)) : undefined
        if (index % 2 === 0) return <span key={index}>{part}</span>
        if (!citation) return <span key={index}>[{part}]</span>
        return (
          <button
            key={index}
            type="button"
            className="cite"
            onClick={() => onCite(citation)}
            aria-label={`Show source ${citation.number}`}
          >
            [{citation.number}]
          </button>
        )
      })}
    </p>
  )
}

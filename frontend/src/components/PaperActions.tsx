import { useState } from 'react'
import { api, messageOf } from '../api'
import type { PaperStatus } from '../types'
import { ErrorMessage } from './ErrorMessage'

interface Props {
  paperId: number
  status: PaperStatus
  onChanged: () => void
  /** Also offer re-running the pipeline for papers that are already indexed. */
  allowRerun?: boolean
}

type Step = 'idle' | 'processing' | 'indexing'

/**
 * Runs the remaining pipeline steps for a paper:
 * imported/failed -> process (PDF to passages) -> index (embeddings); processed -> index.
 */
export function PaperActions({ paperId, status, onChanged, allowRerun = false }: Props) {
  const [step, setStep] = useState<Step>('idle')
  const [error, setError] = useState<string | null>(null)

  const needsProcessing = status === 'imported' || status === 'failed' || status === 'indexed'
  const label =
    status === 'processed' ? 'Index' : status === 'indexed' ? 'Reprocess' : 'Process & index'

  if (status === 'indexed' && !allowRerun) return null

  async function run() {
    setError(null)
    try {
      if (needsProcessing) {
        setStep('processing')
        await api.processPaper(paperId)
      }
      setStep('indexing')
      await api.indexPaper(paperId)
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setStep('idle')
      onChanged() // refresh, so the new status (or the failure) is shown
    }
  }

  return (
    <div className="paper-actions">
      <button type="button" onClick={run} disabled={step !== 'idle'} aria-busy={step !== 'idle'}>
        {step === 'processing' && 'Processing PDF…'}
        {step === 'indexing' && 'Indexing passages…'}
        {step === 'idle' && label}
      </button>
      {error && <ErrorMessage message={error} />}
    </div>
  )
}

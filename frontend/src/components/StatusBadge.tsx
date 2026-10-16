import type { PaperStatus } from '../types'

const LABELS: Record<PaperStatus, string> = {
  imported: 'Imported',
  processed: 'Processed',
  indexed: 'Indexed',
  failed: 'Failed',
}

const DESCRIPTIONS: Record<PaperStatus, string> = {
  imported: 'Metadata only. Process the paper to extract its text.',
  processed: 'Text extracted into passages, but not yet searchable.',
  indexed: 'Searchable and ready for questions.',
  failed: 'The last processing step failed.',
}

export function StatusBadge({ status }: { status: PaperStatus }) {
  // The label is text (not only color), so it is readable for everyone.
  return (
    <span className={`badge badge-${status}`} title={DESCRIPTIONS[status]}>
      {LABELS[status]}
    </span>
  )
}

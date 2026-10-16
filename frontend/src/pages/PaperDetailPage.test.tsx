import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makePaper, mockApi } from '../test/mockApi'
import { renderAt } from '../test/render'
import { PaperDetailPage } from './PaperDetailPage'

const DETAIL = {
  ...makePaper(),
  abstract: 'The dominant sequence transduction models are based on complex networks.',
  source_url: 'https://arxiv.org/abs/1706.03762',
  pdf_url: 'https://arxiv.org/pdf/1706.03762',
  processing_error: null,
  created_at: '2026-10-15T10:00:00Z',
  updated_at: '2026-10-15T10:00:00Z',
}

describe('PaperDetailPage', () => {
  it('shows metadata, abstract and passages', async () => {
    mockApi({
      'GET /papers/1': { body: DETAIL },
      'GET /papers/1/passages': {
        body: [
          { id: 10, position: 0, text: 'First passage text.', page: 1, section: null },
          { id: 11, position: 1, text: 'Second passage text.', page: 2, section: null },
        ],
      },
    })

    renderAt(<PaperDetailPage />, '/papers/1', '/papers/:paperId')

    expect(
      await screen.findByRole('heading', { name: 'Attention Is All You Need' }),
    ).toBeInTheDocument()
    expect(screen.getByText(DETAIL.abstract)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'PDF' })).toHaveAttribute('href', DETAIL.pdf_url)
    expect(await screen.findByText('Second passage text.')).toBeInTheDocument()
    expect(screen.getByText('Passage 2 · page 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reprocess' })).toBeInTheDocument()
  })

  it('shows the last processing error', async () => {
    mockApi({
      'GET /papers/1': {
        body: { ...DETAIL, ingestion_status: 'failed', processing_error: 'PDF is too large.' },
      },
      'GET /papers/1/passages': { body: [] },
    })

    renderAt(<PaperDetailPage />, '/papers/1', '/papers/:paperId')

    expect(await screen.findByText('Last error: PDF is too large.')).toBeInTheDocument()
    expect(await screen.findByText(/No passages yet/)).toBeInTheDocument()
  })

  it('shows not found', async () => {
    mockApi({
      'GET /papers/9': { status: 404, body: { detail: 'Paper not found' } },
      'GET /papers/9/passages': { status: 404, body: { detail: 'Paper not found' } },
    })

    renderAt(<PaperDetailPage />, '/papers/9', '/papers/:paperId')

    expect(await screen.findByRole('alert')).toHaveTextContent('Paper not found')
  })
})

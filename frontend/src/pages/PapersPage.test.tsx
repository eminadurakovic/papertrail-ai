import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { deferred, makePaper, mockApi } from '../test/mockApi'
import { renderAt } from '../test/render'
import { PapersPage } from './PapersPage'

describe('PapersPage', () => {
  it('lists papers with their details', async () => {
    mockApi({ 'GET /papers': { body: [makePaper()] } })

    renderAt(<PapersPage />)

    const card = (await screen.findByRole('link', { name: 'Attention Is All You Need' })).closest(
      'li',
    )!
    const scope = within(card)
    expect(scope.getByText('Ashish Vaswani, Noam Shazeer, Niki Parmar et al.')).toBeInTheDocument()
    expect(scope.getByText('12 Jun 2017')).toBeInTheDocument()
    expect(scope.getByText('1706.03762')).toBeInTheDocument()
    expect(scope.getByText('51')).toBeInTheDocument()
    expect(scope.getByText('Indexed')).toBeInTheDocument()
    expect(scope.queryByRole('button')).not.toBeInTheDocument() // nothing left to do
  })

  it('shows an empty state', async () => {
    mockApi({ 'GET /papers': { body: [] } })

    renderAt(<PapersPage />)

    expect(await screen.findByText(/No papers yet/)).toBeInTheDocument()
  })

  it('shows backend errors', async () => {
    mockApi({ 'GET /papers': { status: 500, body: { detail: 'Database unavailable' } } })

    renderAt(<PapersPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable')
  })

  it('shows a clear message when the backend is not running', async () => {
    mockApi({ 'GET /papers': { status: 502, body: null } })

    renderAt(<PapersPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the backend')
  })

  it('processes and indexes a paper, showing each step', async () => {
    let status: 'imported' | 'indexed' = 'imported'
    const processing = deferred()
    const indexing = deferred()
    const calls = mockApi({
      'GET /papers': () => ({ body: [makePaper({ ingestion_status: status, passage_count: 0 })] }),
      'POST /papers/1/process': processing.route,
      'POST /papers/1/index': indexing.route,
    })
    renderAt(<PapersPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Process & index' }))
    expect(screen.getByRole('button', { name: 'Processing PDF…' })).toBeDisabled()

    processing.resolve({ body: {} })
    expect(await screen.findByRole('button', { name: 'Indexing passages…' })).toBeDisabled()

    status = 'indexed'
    indexing.resolve({ body: {} })
    expect(await screen.findByText('Indexed')).toBeInTheDocument()
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      'GET /papers',
      'POST /papers/1/process',
      'POST /papers/1/index',
      'GET /papers',
    ])
  })

  it('only indexes a paper that is already processed', async () => {
    const calls = mockApi({
      'GET /papers': { body: [makePaper({ ingestion_status: 'processed' })] },
      'POST /papers/1/index': { body: {} },
    })
    renderAt(<PapersPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Index' }))

    await waitFor(() => expect(calls.some((c) => c.path === '/papers/1/index')).toBe(true))
    expect(calls.some((c) => c.path === '/papers/1/process')).toBe(false)
  })

  it('shows a processing error', async () => {
    mockApi({
      'GET /papers': { body: [makePaper({ ingestion_status: 'imported' })] },
      'POST /papers/1/process': {
        status: 422,
        body: { detail: 'No text could be extracted from the PDF.' },
      },
    })
    renderAt(<PapersPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Process & index' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No text could be extracted')
  })
})

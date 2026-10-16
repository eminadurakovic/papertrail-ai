import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { deferred, makePaper, mockApi } from '../test/mockApi'
import { ImportForm } from './ImportForm'

const imported = { created: true, paper: { ...makePaper(), abstract: '' } }

describe('ImportForm', () => {
  it('imports a paper and reports success', async () => {
    const calls = mockApi({ 'POST /papers/import': { status: 201, body: imported } })
    const onImported = vi.fn()
    render(<ImportForm onImported={onImported} />)

    await userEvent.type(screen.getByLabelText('arXiv ID'), '  1706.03762 ')
    await userEvent.click(screen.getByRole('button', { name: 'Import paper' }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Imported “Attention Is All You Need”.',
    )
    expect(calls[0].body).toEqual({ arxiv_id: '1706.03762' }) // trimmed
    expect(onImported).toHaveBeenCalledOnce()
    expect(screen.getByLabelText('arXiv ID')).toHaveValue('')
  })

  it('says when a paper was already imported', async () => {
    mockApi({ 'POST /papers/import': { body: { ...imported, created: false } } })
    render(<ImportForm onImported={() => {}} />)

    await userEvent.type(screen.getByLabelText('arXiv ID'), '1706.03762')
    await userEvent.click(screen.getByRole('button', { name: 'Import paper' }))

    expect(await screen.findByRole('status')).toHaveTextContent('was already imported')
  })

  it('shows the backend error message', async () => {
    mockApi({
      'POST /papers/import': {
        status: 422,
        body: { detail: "'hello' is not a valid arXiv ID. Expected something like 2403.12345." },
      },
    })
    const onImported = vi.fn()
    render(<ImportForm onImported={onImported} />)

    await userEvent.type(screen.getByLabelText('arXiv ID'), 'hello')
    await userEvent.click(screen.getByRole('button', { name: 'Import paper' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("'hello' is not a valid arXiv ID")
    expect(onImported).not.toHaveBeenCalled()
  })

  it('asks for an ID instead of sending an empty request', async () => {
    const calls = mockApi({})
    render(<ImportForm onImported={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: 'Import paper' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Enter an arXiv ID')
    expect(calls).toEqual([])
  })

  it('disables the form while importing', async () => {
    const pending = deferred()
    mockApi({ 'POST /papers/import': pending.route })
    render(<ImportForm onImported={() => {}} />)

    await userEvent.type(screen.getByLabelText('arXiv ID'), '1706.03762')
    await userEvent.click(screen.getByRole('button', { name: 'Import paper' }))

    expect(screen.getByRole('button', { name: 'Importing…' })).toBeDisabled()
    expect(screen.getByLabelText('arXiv ID')).toBeDisabled()
    pending.resolve({ status: 201, body: imported })
    expect(await screen.findByRole('button', { name: 'Import paper' })).toBeEnabled()
  })
})

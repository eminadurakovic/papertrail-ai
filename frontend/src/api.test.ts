import { describe, expect, it, vi } from 'vitest'
import { api, ApiError, errorMessage } from './api'

describe('errorMessage', () => {
  it('uses a string detail as-is', () => {
    expect(errorMessage({ detail: 'Paper not found' }, 404)).toBe('Paper not found')
  })

  it('summarises validation errors', () => {
    const body = { detail: [{ msg: 'String should have at least 1 character' }] }
    expect(errorMessage(body, 422)).toBe('Invalid request: String should have at least 1 character')
  })

  it('explains a missing backend', () => {
    expect(errorMessage(null, 502)).toMatch('Cannot reach the backend')
  })

  it('falls back to the status code', () => {
    expect(errorMessage({ other: true }, 418)).toBe('Request failed (HTTP 418).')
  })
})

describe('api', () => {
  it('turns network failures into a readable ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(api.listPapers()).rejects.toEqual(
      new ApiError('Cannot reach the backend. Is it running on port 8001?', 0),
    )
  })
})

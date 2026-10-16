import { vi } from 'vitest'
import type { AskResponse, Citation, PaperSummary } from '../types'

interface MockResponse {
  status?: number
  body?: unknown
}

type Route = MockResponse | (() => MockResponse | Promise<MockResponse>)

export interface Call {
  method: string
  path: string
  body: unknown
}

/**
 * Replaces global fetch. Routes are keyed "METHOD /path" (without the /api prefix and query
 * string). A route can be a response or a function returning one, possibly asynchronously.
 * Returns the list of calls, so tests can check what the UI sent.
 */
export function mockApi(routes: Record<string, Route>): Call[] {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const path = input.replace(/^\/api/, '').split('?')[0]
      calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      const route = routes[`${method} ${path}`]
      if (route === undefined) throw new Error(`Unmocked request: ${method} ${path}`)
      const { status = 200, body = null } = typeof route === 'function' ? await route() : route
      return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
  return calls
}

/** A response the test resolves later, to observe loading states. */
export function deferred(): { route: () => Promise<MockResponse>; resolve: (r: MockResponse) => void } {
  let resolve!: (response: MockResponse) => void
  const promise = new Promise<MockResponse>((r) => (resolve = r))
  return { route: () => promise, resolve }
}

export function makePaper(overrides: Partial<PaperSummary> = {}): PaperSummary {
  return {
    id: 1,
    arxiv_id: '1706.03762',
    title: 'Attention Is All You Need',
    published_date: '2017-06-12',
    ingestion_status: 'indexed',
    authors: [
      { id: 1, name: 'Ashish Vaswani' },
      { id: 2, name: 'Noam Shazeer' },
      { id: 3, name: 'Niki Parmar' },
      { id: 4, name: 'Jakob Uszkoreit' },
    ],
    passage_count: 51,
    ...overrides,
  }
}

export function makeCitation(overrides: Partial<Citation> = {}): Citation {
  return {
    number: 1,
    paper_id: 1,
    paper_title: 'Attention Is All You Need',
    arxiv_id: '1706.03762',
    passage_id: 71,
    position: 19,
    page: 6,
    passage_text: 'we use sine and cosine functions of different frequencies',
    score: 0.809,
    ...overrides,
  }
}

export function makeAnswer(overrides: Partial<AskResponse> = {}): AskResponse {
  return {
    answer: 'They use sine and cosine functions [1].',
    abstained: false,
    abstention_reason: null,
    citations: [makeCitation()],
    best_score: 0.809,
    ...overrides,
  }
}

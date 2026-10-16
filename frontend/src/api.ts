import type {
  AskResponse,
  ImportResponse,
  IndexResponse,
  Info,
  PaperDetail,
  PaperSummary,
  Passage,
  ProcessResponse,
} from './types'

// Forwarded to the backend by the Vite dev/preview server (see vite.config.ts).
const API_BASE = '/api'

/** A failed request, with a message that is safe and useful to show to the user. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const BACKEND_DOWN = 'Cannot reach the backend. Is it running on port 8001?'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(API_BASE + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(BACKEND_DOWN, 0)
  }

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(errorMessage(body, response.status), response.status)
  }
  return body as T
}

/** FastAPI errors look like {"detail": "..."} or, for validation, {"detail": [{msg}]}. */
export function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
    return `Invalid request: ${detail[0].msg}`
  }
  // No JSON body usually means the dev-server proxy couldn't reach the backend.
  if (body === null && status >= 500) return BACKEND_DOWN
  return `Request failed (HTTP ${status}).`
}

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  health: () => request<{ status: string }>('/health'),
  info: () => request<Info>('/info'),
  listPapers: () => request<PaperSummary[]>('/papers?limit=200'),
  getPaper: (paperId: number) => request<PaperDetail>(`/papers/${paperId}`),
  listPassages: (paperId: number) => request<Passage[]>(`/papers/${paperId}/passages`),
  importPaper: (arxivId: string) =>
    request<ImportResponse>('/papers/import', post({ arxiv_id: arxivId })),
  processPaper: (paperId: number) =>
    request<ProcessResponse>(`/papers/${paperId}/process`, post()),
  indexPaper: (paperId: number) => request<IndexResponse>(`/papers/${paperId}/index`, post()),
  ask: (question: string, paperIds: number[]) =>
    request<AskResponse>('/ask', post({ question, paper_ids: paperIds })),
}

export function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
}

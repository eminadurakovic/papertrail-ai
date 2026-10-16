import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockApi } from '../test/mockApi'
import { renderAt } from '../test/render'
import { AboutPage } from './AboutPage'

const INFO = {
  app_name: 'PaperTrail AI',
  version: '0.1.0',
  embedding_model: 'BAAI/bge-small-en-v1.5',
  embedding_dimension: 384,
  llm_provider: 'ollama',
  llm_model: 'qwen2.5:7b',
  rag_min_score: 0.7,
  chunk_size_words: 150,
  chunk_overlap_words: 30,
}

describe('AboutPage', () => {
  it('shows backend health and model configuration', async () => {
    mockApi({ 'GET /health': { body: { status: 'ok' } }, 'GET /info': { body: INFO } })

    renderAt(<AboutPage />)

    expect(await screen.findByText('OK')).toBeInTheDocument()
    expect(await screen.findByText('BAAI/bge-small-en-v1.5 (384 dimensions)')).toBeInTheDocument()
    expect(screen.getByText('qwen2.5:7b via ollama')).toBeInTheDocument()
    expect(screen.getByText('similarity ≥ 0.70')).toBeInTheDocument()
    expect(screen.getByText('150 words, 30 overlap')).toBeInTheDocument()
  })

  it('says when no language model is configured', async () => {
    mockApi({
      'GET /health': { body: { status: 'ok' } },
      'GET /info': { body: { ...INFO, llm_provider: 'none', llm_model: null } },
    })

    renderAt(<AboutPage />)

    expect(await screen.findByText('Not configured (answers disabled)')).toBeInTheDocument()
  })

  it('shows when the backend is down', async () => {
    mockApi({ 'GET /health': { status: 502, body: null }, 'GET /info': { status: 502, body: null } })

    renderAt(<AboutPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Backend: Cannot reach the backend')
  })
})

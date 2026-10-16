import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { deferred, makeAnswer, makeCitation, makePaper, mockApi } from '../test/mockApi'
import { renderAt } from '../test/render'
import { AskPage } from './AskPage'

const PAPERS = [
  makePaper(),
  makePaper({ id: 2, title: 'BERT', arxiv_id: '1810.04805' }),
  makePaper({ id: 3, title: 'Not indexed yet', ingestion_status: 'processed' }),
]

async function ask(question: string) {
  await userEvent.type(screen.getByLabelText('Question'), question)
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

describe('AskPage', () => {
  it('shows the answer with clickable citations and sources', async () => {
    const calls = mockApi({ 'GET /papers': { body: PAPERS }, 'POST /ask': { body: makeAnswer() } })
    renderAt(<AskPage />)

    await ask('How are positional encodings computed?')

    const answer = await screen.findByRole('heading', { name: 'Answer' })
    expect(answer.parentElement).toHaveTextContent('They use sine and cosine functions [1].')
    expect(screen.getByRole('button', { name: 'Show source 1' })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '[1] Attention Is All You Need, page 6' }),
    ).toBeInTheDocument()
    expect(calls.at(-1)).toEqual({
      method: 'POST',
      path: '/ask',
      body: { question: 'How are positional encodings computed?', paper_ids: [] },
    })
  })

  it('opens the exact source passage when a citation is clicked, and closes it', async () => {
    mockApi({ 'GET /papers': { body: PAPERS }, 'POST /ask': { body: makeAnswer() } })
    renderAt(<AskPage />)
    await ask('How are positional encodings computed?')

    await userEvent.click(await screen.findByRole('button', { name: 'Show source 1' }))

    const panel = screen.getByRole('dialog', { name: 'Source [1]' })
    expect(within(panel).getByText(makeCitation().passage_text)).toBeInTheDocument()
    expect(within(panel).getByText(/Page 6 · Passage 20 · similarity 0.81/)).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: 'Attention Is All You Need' })).toHaveAttribute(
      'href',
      '/papers/1',
    )
    expect(within(panel).getByRole('button', { name: 'Close' })).toHaveFocus()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens the right source when there are several', async () => {
    const second = makeCitation({ number: 2, passage_id: 99, passage_text: 'second source text' })
    mockApi({
      'GET /papers': { body: PAPERS },
      'POST /ask': {
        body: makeAnswer({ answer: 'A [1] and B [2].', citations: [makeCitation(), second] }),
      },
    })
    renderAt(<AskPage />)
    await ask('question')

    await userEvent.click(await screen.findByRole('button', { name: 'Show source 2' }))

    expect(screen.getByRole('dialog', { name: 'Source [2]' })).toHaveTextContent(
      'second source text',
    )
  })

  it('shows abstention clearly, without sources', async () => {
    mockApi({
      'GET /papers': { body: PAPERS },
      'POST /ask': {
        body: makeAnswer({
          answer: 'I could not find enough evidence in the imported papers to answer this question.',
          abstained: true,
          abstention_reason: 'no_relevant_passages',
          citations: [],
          best_score: 0.47,
        }),
      },
    })
    renderAt(<AskPage />)

    await ask('What is a good recipe for sourdough bread?')

    const notice = await screen.findByRole('heading', { name: 'Not enough evidence' })
    expect(notice.parentElement).toHaveTextContent('I could not find enough evidence')
    expect(notice.parentElement).toHaveTextContent('Best similarity found: 0.47.')
    expect(screen.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
  })

  it('filters by one paper, offering only indexed papers', async () => {
    const calls = mockApi({ 'GET /papers': { body: PAPERS }, 'POST /ask': { body: makeAnswer() } })
    renderAt(<AskPage />)
    const filter = screen.getByLabelText('Search in')
    await screen.findByRole('option', { name: 'BERT' })

    expect(within(filter).queryByRole('option', { name: 'Not indexed yet' })).toBeNull()
    await userEvent.selectOptions(filter, 'BERT')
    await ask('What is masked language modeling?')

    await screen.findByRole('heading', { name: 'Answer' })
    expect(calls.at(-1)?.body).toEqual({
      question: 'What is masked language modeling?',
      paper_ids: [2],
    })
  })

  it('shows backend errors such as a missing language model', async () => {
    mockApi({
      'GET /papers': { body: PAPERS },
      'POST /ask': {
        status: 503,
        body: { detail: 'Could not reach Ollama at http://localhost:11434.' },
      },
    })
    renderAt(<AskPage />)

    await ask('How are positional encodings computed?')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach Ollama')
  })

  it('cannot submit an empty question and shows progress while answering', async () => {
    const pending = deferred()
    mockApi({ 'GET /papers': { body: PAPERS }, 'POST /ask': pending.route })
    renderAt(<AskPage />)

    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Question'), '   ')
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()

    await ask('real question')
    expect(screen.getByRole('button', { name: 'Searching and answering…' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('can take 5–20 seconds')

    pending.resolve({ body: makeAnswer() })
    expect(await screen.findByRole('heading', { name: 'Answer' })).toBeInTheDocument()
  })
})

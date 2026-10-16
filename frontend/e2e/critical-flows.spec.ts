import { expect, test } from '@playwright/test'

const ARXIV_ID = '1706.03762'
const TITLE = 'Attention Is All You Need'

// Make sure one known paper exists and is indexed. Importing is idempotent, so this only
// contacts arXiv the first time; afterwards it is a no-op.
test.beforeAll(async ({ request }) => {
  const imported = await request.post('/api/papers/import', { data: { arxiv_id: ARXIV_ID } })
  expect(imported.ok()).toBeTruthy()
  const { paper } = await imported.json()
  if (paper.ingestion_status !== 'indexed') {
    expect((await request.post(`/api/papers/${paper.id}/process`)).ok()).toBeTruthy()
    expect((await request.post(`/api/papers/${paper.id}/index`)).ok()).toBeTruthy()
  }
})

test('papers page lists the paper and its detail page shows passages', async ({ page }) => {
  await page.goto('/')

  const card = page.getByRole('listitem').filter({ hasText: TITLE })
  await expect(card.getByText('Indexed')).toBeVisible()
  await expect(card.getByText(ARXIV_ID)).toBeVisible()

  await card.getByRole('link', { name: TITLE }).click()
  await expect(page.getByRole('heading', { name: TITLE, level: 1 })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Abstract' })).toBeVisible()
  await expect(page.getByText(/^Passage 1 · page 1$/)).toBeVisible()
})

test('asking an answerable question gives a cited answer whose source can be opened', async ({
  page,
}) => {
  await page.goto('/ask')
  await page.getByLabel('Question').fill('How are positional encodings computed in the Transformer?')
  await page.getByRole('button', { name: 'Ask' }).click()

  await expect(page.getByRole('heading', { name: 'Answer' })).toBeVisible({ timeout: 90_000 })
  const firstCitation = page.getByRole('button', { name: /^Show source \d+$/ }).first()
  await firstCitation.click()

  const panel = page.getByRole('dialog')
  await expect(panel).toBeVisible()
  await expect(panel.getByRole('link', { name: TITLE })).toBeVisible()
  await expect(panel.locator('blockquote')).toContainText(/sine|cosine|position/i)

  await page.keyboard.press('Escape')
  await expect(panel).toBeHidden()
})

test('an unrelated question abstains', async ({ page }) => {
  await page.goto('/ask')
  await page.getByLabel('Question').fill('What is a good recipe for sourdough bread?')
  await page.getByRole('button', { name: 'Ask' }).click()

  await expect(page.getByRole('heading', { name: 'Not enough evidence' })).toBeVisible()
  await expect(page.getByText(/could not find enough evidence/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Sources' })).toHaveCount(0)
})

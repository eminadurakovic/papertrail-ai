import type { Author } from './types'

/** "2017-06-12" -> "12 Jun 2017" (UTC, so the day never shifts with the browser's timezone). */
export function formatDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/** First three authors, then "et al." */
export function formatAuthors(authors: Author[]): string {
  const names = authors.map((author) => author.name)
  return names.length > 3 ? `${names.slice(0, 3).join(', ')} et al.` : names.join(', ')
}

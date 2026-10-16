// Shapes of the backend's JSON responses (see backend/app/schemas/).

export type PaperStatus = 'imported' | 'processed' | 'indexed' | 'failed'

export interface Author {
  id: number
  name: string
}

export interface PaperSummary {
  id: number
  arxiv_id: string
  title: string
  published_date: string // YYYY-MM-DD
  ingestion_status: PaperStatus
  authors: Author[]
  passage_count: number
}

export interface PaperDetail extends PaperSummary {
  abstract: string
  source_url: string
  pdf_url: string
  processing_error: string | null
  created_at: string
  updated_at: string
}

export interface Passage {
  id: number
  position: number
  text: string
  page: number | null
  section: string | null
}

export interface ImportResponse {
  created: boolean
  paper: PaperDetail
}

export interface ProcessResponse {
  paper_id: number
  ingestion_status: PaperStatus
  page_count: number
  extracted_characters: number
  passage_count: number
}

export interface IndexResponse {
  paper_id: number
  ingestion_status: PaperStatus
  indexed_passages: number
  embedding_dimension: number
  embedding_model: string
}

export interface Citation {
  number: number
  paper_id: number
  paper_title: string
  arxiv_id: string
  passage_id: number
  position: number
  page: number | null
  passage_text: string
  score: number
}

export type AbstentionReason =
  | 'no_relevant_passages'
  | 'model_insufficient_evidence'
  | 'no_valid_citations'

export interface AskResponse {
  answer: string
  abstained: boolean
  abstention_reason: AbstentionReason | null
  citations: Citation[]
  best_score: number | null
}

export interface Info {
  app_name: string
  version: string
  embedding_model: string
  embedding_dimension: number
  llm_provider: string
  llm_model: string | null
  rag_min_score: number
  chunk_size_words: number
  chunk_overlap_words: number
}

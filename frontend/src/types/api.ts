// ── Generic Pagination ──
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
}

// ── Auth ──
export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserInfo {
  id: number
  username: string
  email: string
  role: string
}

// ── Knowledge Base ──
export interface KnowledgeBaseItem {
  id: number
  name: string
  description: string | null
  user_id: number
  workspace_id: number | null
  embedding_model_id: number | null
  chunk_strategy: string
  chunk_size: number
  chunk_overlap: number
  search_mode: string
  doc_count: number
  chunk_count: number
  processing_count: number
  failed_count: number
  welcome_message: string | null
  suggested_questions: string | null
  prompt_template: string | null
  created_at: string
  updated_at: string
  workspace_name: string | null
  access_role: string
  can_write: boolean
  can_manage: boolean
}

// ── Document ──
export interface DocumentItem {
  id: number
  kb_id: number
  filename: string
  status: string
  chunk_count: number
  file_size: number | null
  error_message: string | null
  created_at: string
  updated_at: string
  file_type?: string
  auto_tags?: string[] | null
  content_hash?: string | null
  expires_at?: string | null
  is_archived?: boolean
}

export interface DocumentChunkItem {
  id: number
  doc_id: number
  kb_id: number
  chunk_index: number
  content: string
}

// ── Model Config ──
export interface ModelConfigItem {
  id: number
  user_id: number
  display_name: string
  model_type: string
  provider: string
  model_name: string
  api_base: string | null
  api_key_set?: boolean
  is_default: boolean
  created_at: string
}

// ── Chat ──
export interface ConversationItem {
  id: number
  title: string
  kb_id: number
  llm_model_id: number | null
  total_input_tokens: number
  total_output_tokens: number
  is_pinned: boolean
  created_at: string
  updated_at: string
}

export interface ChatMessageItem {
  id: number
  conversation_id: number
  role: 'user' | 'assistant'
  content: string
  references: string | null
  feedback: string | null
  feedback_reason: string | null
  token_count: number | null
  latency_ms: number | null
  created_at: string
}

export interface RetrievalResultItem {
  content: string
  score: number
  doc_id: number
  doc_name: string
  chunk_index: number
  kb_id: number
}

export interface StreamEvent {
  type: 'mode' | 'status' | 'references' | 'content' | 'error' | 'done'
    | 'sql' | 'sql_error' | 'tool_call' | 'tool_result' | 'agent_complete'
    | 'agent_dispatch' | 'agent_result'
  data?: any
  conversation_id?: number
  latency_ms?: number
  usage?: { input_tokens: number; output_tokens: number }
}

export interface ConversationSearchResult {
  id: number
  title: string
  kb_id: number
  created_at: string
  matching_messages: Array<{ role: string; snippet: string }>
}

// ── Usage ──
export interface UsageSummary {
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  conversation_count: number
  by_model: Array<{
    model_id: number | null
    model_name: string
    input_tokens: number
    output_tokens: number
    total_tokens: number
    conversations: number
  }>
}

// ── Common API response ──
export interface MessageResponse {
  message: string
}

export interface BatchDeleteResponse {
  message: string
  deleted: number
}

// ── Usage Trend ──
export interface UsageTrendItem {
  date: string
  tokens: number
  message_count: number
}

export interface UsageTrendResponse {
  days: number
  trend: UsageTrendItem[]
}

// ── Feedback ──
export type FeedbackType = 'like' | 'dislike'
export type LikeFeedbackReason = 'accurate' | 'helpful' | 'well_written' | 'creative'
export type DislikeFeedbackReason = 'inaccurate' | 'irrelevant' | 'incomplete' | 'harmful' | 'too_long'
export type FeedbackReason = LikeFeedbackReason | DislikeFeedbackReason

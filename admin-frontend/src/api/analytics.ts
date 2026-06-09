/**
 * 运营分析 API。
 */
import request from '../utils/request'

export interface OverviewData {
  period: string
  conversations: { total: number; change: number }
  messages: { total: number; change: number }
  active_users: { total: number; change: number }
  satisfaction: { rate: number; positive: number; negative: number }
}

export interface TrendPoint {
  date: string
  value: number
}

export interface TrendData {
  metric: string
  period: string
  data: TrendPoint[]
}

export interface KnowledgeBaseStats {
  id: number
  name: string
  conversation_count: number
}

export interface TopQuestion {
  question: string
  count: number
}

export interface LowSatisfactionMessage {
  id: number
  content: string
  feedback: string
  created_at: string
  knowledge_base_id: number
}

/**
 * 获取运营概览数据。
 */
export function getOverview(period: string = '7d'): Promise<OverviewData> {
  return request.get('/analytics/overview', { params: { period } })
}

/**
 * 获取趋势数据。
 */
export function getTrends(metric: string = 'conversations', period: string = '30d'): Promise<TrendData> {
  return request.get('/analytics/trends', { params: { metric, period } })
}

/**
 * 获取知识库统计排行。
 */
export function getKnowledgeBaseStats(
  sort: string = 'conversations',
  order: string = 'desc',
  limit: number = 10
): Promise<{ items: KnowledgeBaseStats[] }> {
  return request.get('/analytics/knowledge-bases', { params: { sort, order, limit } })
}

/**
 * 获取高频问题。
 */
export function getTopQuestions(limit: number = 10): Promise<{ items: TopQuestion[] }> {
  return request.get('/analytics/top-questions', { params: { limit } })
}

/**
 * 获取低评分消息。
 */
export function getLowSatisfactionMessages(limit: number = 20): Promise<{ items: LowSatisfactionMessage[] }> {
  return request.get('/analytics/low-satisfaction', { params: { limit } })
}

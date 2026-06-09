import request from '../utils/request'

export interface AddWebSourceParams {
  kb_id: number
  url: string
  source_type?: 'html' | 'json' | 'rss' | 'sitemap'
  crawl_interval_hours?: number | null
  auto_reindex?: boolean
  use_browser?: boolean
}

export function addWebSource(data: AddWebSourceParams) {
  return request.post('/web-sources/', data)
}

export function listWebSources(kbId: number) {
  return request.get(`/web-sources/${kbId}`)
}

export function recrawlWebSource(sourceId: number) {
  return request.post(`/web-sources/${sourceId}/recrawl`)
}

export function deleteWebSource(sourceId: number) {
  return request.delete(`/web-sources/${sourceId}`)
}

export function updateWebSourceSchedule(
  sourceId: number,
  data: { crawl_interval_hours: number | null; auto_reindex: boolean }
) {
  return request.put(`/web-sources/${sourceId}/schedule`, data)
}

export function getCrawlStatus(kbId: number) {
  return request.get(`/web-sources/${kbId}/crawl-status`)
}

export function getWebSourceContent(sourceId: number) {
  return request.get(`/web-sources/source/${sourceId}/content`)
}

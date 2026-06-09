import request from '../utils/request'

export interface DatabaseSourceForm {
  kb_id: number
  name: string
  db_type: 'postgresql' | 'mysql'
  host?: string
  port?: number
  database_name?: string
  schema_name?: string
  username?: string
  password?: string
  table_names?: string[]
  column_filter?: Record<string, string[]>
  row_limit?: number
}

export interface DatabaseSourceItem {
  id: number
  kb_id: number
  name: string
  db_type: string
  host?: string
  port?: number
  database_name?: string
  schema_name?: string
  username?: string
  table_names: string[]
  column_filter?: Record<string, string[]>
  row_limit: number
  has_password: boolean
  status: string
  last_synced_at?: string
  last_error?: string
  created_at: string
  updated_at: string
}

export interface DatabaseTableInfo {
  name: string
  kind: string
  columns: { name: string; type: string }[]
}

export function listAllDatabaseSources() {
  return request.get<DatabaseSourceItem[]>('/database-sources/')
}

export interface DiscoveredDatabase {
  db_type: string
  host?: string
  port?: number
  database_name: string
  username?: string
  has_password?: boolean
  table_count: number
}

export function scanLocalDatabases() {
  return request.get<{ databases: DiscoveredDatabase[] }>('/database-sources/scan', { _silentError: true } as any)
}

export function listDatabaseSources(kbId: number) {
  return request.get<DatabaseSourceItem[]>(`/database-sources/kb/${kbId}`)
}

export function getDatabaseSource(sourceId: number) {
  return request.get<DatabaseSourceItem>(`/database-sources/${sourceId}`)
}

export function createDatabaseSource(data: DatabaseSourceForm) {
  return request.post<DatabaseSourceItem>('/database-sources/', data, { _silentError: true } as any)
}

export function updateDatabaseSource(sourceId: number, data: Partial<DatabaseSourceForm>) {
  return request.put<DatabaseSourceItem>(`/database-sources/${sourceId}`, data)
}

export function deleteDatabaseSource(sourceId: number) {
  return request.delete(`/database-sources/${sourceId}`)
}

export function testDatabaseConnection(data: Omit<DatabaseSourceForm, 'kb_id' | 'name'>) {
  return request.post('/database-sources/test', data, { _silentError: true } as any)
}

export interface ServerConnectRequest {
  db_type: 'postgresql' | 'mysql'
  host: string
  port?: number
  username: string
  password?: string
}

export interface ServerDatabase {
  database_name: string
  table_count: number
}

export function listServerDatabases(data: ServerConnectRequest) {
  return request.post<{ databases: ServerDatabase[]; message: string }>('/database-sources/list-databases', data, { _silentError: true } as any)
}

export function testSavedDatabaseConnection(sourceId: number) {
  return request.post(`/database-sources/${sourceId}/test`, null, { _silentError: true } as any)
}

export function listDatabaseTables(sourceId: number) {
  return request.get<DatabaseTableInfo[]>(`/database-sources/${sourceId}/tables`)
}

export function syncDatabaseSource(sourceId: number) {
  return request.post(`/database-sources/${sourceId}/sync`, null, { _silentError: true } as any)
}

export interface SyncRunItem {
  id: number
  source_id: number
  status: string
  table_count: number
  row_count: number
  chunk_count: number
  duration_seconds?: number
  tables_detail?: string
  error_message?: string
  started_at?: string
  finished_at?: string
}

export function listSyncRuns(sourceId: number, limit = 20) {
  return request.get<SyncRunItem[]>(`/database-sources/${sourceId}/sync-runs`, { params: { limit } })
}

/**
 * 将日期字符串转换为相对时间描述（如"3分钟前"、"2天前"）
 */
export function relativeTime(dateStr: string): string {
  if (!dateStr || dateStr === 'None') return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins}分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天前`
  return new Date(dateStr).toLocaleDateString()
}

/**
 * 将工作空间角色标识映射为中文显示名称
 */
export function roleLabel(role: string): string {
  const map: Record<string, string> = {
    owner: '所有者',
    admin: '管理员',
    member: '成员',
    viewer: '只读',
  }
  return map[role] || role
}

/**
 * 角色映射表（常量形式，适用于模板直接绑定）
 */
export const roleMap: Record<string, string> = {
  owner: '所有者',
  admin: '管理员',
  member: '成员',
  viewer: '只读',
}

/**
 * 将毫秒数格式化为可读的时间字符串
 */
export function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

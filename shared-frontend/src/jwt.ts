/**
 * JWT 解析与验证工具。
 *
 * 用于解析 JWT payload 和检查 token 是否过期。
 */

/**
 * 解码 JWT payload（不验证签名）。
 *
 * @param token - JWT 字符串
 * @returns 解码后的 payload 对象，解析失败返回 null
 */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    // Valid JWT must have exactly 3 parts (header.payload.signature)
    if (parts.length !== 3) return null

    // Reject alg:none tokens by checking the header
    const headerB64 = parts[0]
    const headerNorm = headerB64.replace(/-/g, '+').replace(/_/g, '/')
    const headerPad = headerNorm.padEnd(headerNorm.length + ((4 - (headerNorm.length % 4)) % 4), '=')
    const header = JSON.parse(atob(headerPad))
    if (!header?.alg || header.alg === 'none') return null

    // Decode payload
    const base64 = parts[1]
    const normalized = base64.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      '='
    )
    const payload = JSON.parse(atob(padded))

    // Validate required claim types
    if (payload.exp !== undefined && typeof payload.exp !== 'number') return null
    if (payload.sub !== undefined && typeof payload.sub !== 'string' && typeof payload.sub !== 'number') return null

    return payload
  } catch {
    return null
  }
}

/**
 * 检查 JWT 是否已过期或即将过期。
 *
 * @param token - JWT 字符串
 * @param bufferMs - 提前多少毫秒视为过期（默认 5000ms）
 * @returns true 表示已过期或即将过期
 */
export function isTokenExpired(token: string, bufferMs = 5000): boolean {
  const payload = decodeJwtPayload(token)
  if (!payload?.exp || typeof payload.exp !== 'number') return true
  return payload.exp * 1000 <= Date.now() + bufferMs
}

/**
 * 从 JWT 中提取用户 ID。
 *
 * @param token - JWT 字符串
 * @returns 用户 ID 字符串，解析失败返回 null
 */
export function getUserIdFromToken(token: string): string | null {
  const payload = decodeJwtPayload(token)
  if (!payload?.sub) return null
  return String(payload.sub)
}

/**
 * 从 JWT 中提取用户角色。
 *
 * @param token - JWT 字符串
 * @returns 用户角色字符串，解析失败返回 null
 */
export function getRoleFromToken(token: string): string | null {
  const payload = decodeJwtPayload(token)
  if (!payload?.role) return null
  return String(payload.role)
}

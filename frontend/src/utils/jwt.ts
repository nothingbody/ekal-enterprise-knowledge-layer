/**
 * Re-export JWT utilities from shared package.
 * This file is kept for backwards compatibility with existing imports.
 */
export {
  decodeJwtPayload,
  isTokenExpired,
  getUserIdFromToken,
  getRoleFromToken,
} from '@rag-platform/shared-utils/jwt'

/**
 * RAG Platform Shared Frontend Utilities
 * 
 * 为 frontend 和 admin-frontend 提供共享工具。
 */

// JWT 工具
export {
  decodeJwtPayload,
  isTokenExpired,
  getUserIdFromToken,
  getRoleFromToken,
} from './jwt'

// 请求工具
export {
  formatErrorDetail,
  createRequestInterceptor,
  createResponseInterceptorFactory,
  createLocalStorageTokens,
  type RequestOptions,
  type TokenStorageKeys,
} from './request'

// 权限工具
export {
  Role,
  Permission,
  ROLE_HIERARCHY,
  ROLE_PERMISSIONS,
  hasPermission,
  hasAnyPermission,
  hasAllPermissions,
  checkRoleLevel,
  getRoleFromString,
  isValidRole,
} from './permissions';

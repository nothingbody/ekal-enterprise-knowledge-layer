/**
 * 权限与角色常量模块。
 * 
 * 与后端 shared/rag_platform_common/permissions.py 保持同步。
 */

/** 用户角色枚举 */
export enum Role {
  SUPER_ADMIN = 'super_admin',
  ADMIN = 'admin',
  ORG_ADMIN = 'org_admin',
  USER = 'user',
  VIEWER = 'viewer',
  GUEST = 'guest',
}

/** 权限枚举 */
export enum Permission {
  // 知识库权限
  KB_READ = 'kb:read',
  KB_WRITE = 'kb:write',
  KB_DELETE = 'kb:delete',
  KB_ADMIN = 'kb:admin',

  // 文档权限
  DOC_READ = 'doc:read',
  DOC_WRITE = 'doc:write',
  DOC_DELETE = 'doc:delete',

  // 对话权限
  CHAT_READ = 'chat:read',
  CHAT_WRITE = 'chat:write',
  CHAT_DELETE = 'chat:delete',

  // 模型配置权限
  MODEL_READ = 'model:read',
  MODEL_WRITE = 'model:write',
  MODEL_DELETE = 'model:delete',

  // 用户管理权限
  USER_READ = 'user:read',
  USER_WRITE = 'user:write',
  USER_DELETE = 'user:delete',

  // 组织管理权限
  ORG_READ = 'org:read',
  ORG_WRITE = 'org:write',
  ORG_DELETE = 'org:delete',

  // 系统管理权限
  SYSTEM_READ = 'system:read',
  SYSTEM_WRITE = 'system:write',
  SYSTEM_ADMIN = 'system:admin',

  // 工作空间权限
  WORKSPACE_READ = 'workspace:read',
  WORKSPACE_WRITE = 'workspace:write',
  WORKSPACE_ADMIN = 'workspace:admin',

  // 技能权限
  SKILL_READ = 'skill:read',
  SKILL_WRITE = 'skill:write',
  SKILL_PUBLISH = 'skill:publish',

  // API 密钥权限
  API_KEY_READ = 'api_key:read',
  API_KEY_WRITE = 'api_key:write',
}

/** 角色层级（数值越大权限越高） */
export const ROLE_HIERARCHY: Record<Role, number> = {
  [Role.SUPER_ADMIN]: 100,
  [Role.ADMIN]: 80,
  [Role.ORG_ADMIN]: 60,
  [Role.USER]: 40,
  [Role.VIEWER]: 20,
  [Role.GUEST]: 10,
};

/** 角色默认权限映射 */
export const ROLE_PERMISSIONS: Record<Role, Set<Permission>> = {
  [Role.GUEST]: new Set([
    Permission.KB_READ,
    Permission.DOC_READ,
    Permission.CHAT_READ,
  ]),
  [Role.VIEWER]: new Set([
    Permission.KB_READ,
    Permission.DOC_READ,
    Permission.CHAT_READ,
    Permission.MODEL_READ,
    Permission.SKILL_READ,
  ]),
  [Role.USER]: new Set([
    Permission.KB_READ,
    Permission.KB_WRITE,
    Permission.DOC_READ,
    Permission.DOC_WRITE,
    Permission.CHAT_READ,
    Permission.CHAT_WRITE,
    Permission.MODEL_READ,
    Permission.SKILL_READ,
    Permission.SKILL_WRITE,
    Permission.WORKSPACE_READ,
    Permission.API_KEY_READ,
    Permission.API_KEY_WRITE,
  ]),
  [Role.ORG_ADMIN]: new Set([
    Permission.KB_READ,
    Permission.KB_WRITE,
    Permission.KB_DELETE,
    Permission.KB_ADMIN,
    Permission.DOC_READ,
    Permission.DOC_WRITE,
    Permission.DOC_DELETE,
    Permission.CHAT_READ,
    Permission.CHAT_WRITE,
    Permission.CHAT_DELETE,
    Permission.MODEL_READ,
    Permission.MODEL_WRITE,
    Permission.USER_READ,
    Permission.USER_WRITE,
    Permission.ORG_READ,
    Permission.SKILL_READ,
    Permission.SKILL_WRITE,
    Permission.WORKSPACE_READ,
    Permission.WORKSPACE_WRITE,
    Permission.API_KEY_READ,
    Permission.API_KEY_WRITE,
  ]),
  [Role.ADMIN]: new Set([
    Permission.KB_READ,
    Permission.KB_WRITE,
    Permission.KB_DELETE,
    Permission.KB_ADMIN,
    Permission.DOC_READ,
    Permission.DOC_WRITE,
    Permission.DOC_DELETE,
    Permission.CHAT_READ,
    Permission.CHAT_WRITE,
    Permission.CHAT_DELETE,
    Permission.MODEL_READ,
    Permission.MODEL_WRITE,
    Permission.MODEL_DELETE,
    Permission.USER_READ,
    Permission.USER_WRITE,
    Permission.USER_DELETE,
    Permission.ORG_READ,
    Permission.ORG_WRITE,
    Permission.SYSTEM_READ,
    Permission.SYSTEM_WRITE,
    Permission.SKILL_READ,
    Permission.SKILL_WRITE,
    Permission.SKILL_PUBLISH,
    Permission.WORKSPACE_READ,
    Permission.WORKSPACE_WRITE,
    Permission.WORKSPACE_ADMIN,
    Permission.API_KEY_READ,
    Permission.API_KEY_WRITE,
  ]),
  [Role.SUPER_ADMIN]: new Set(Object.values(Permission)),
};

/**
 * 检查角色是否拥有指定权限。
 */
export function hasPermission(role: Role, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role]?.has(permission) ?? false;
}

/**
 * 检查角色是否拥有任一指定权限。
 */
export function hasAnyPermission(role: Role, permissions: Permission[]): boolean {
  const rolePerms = ROLE_PERMISSIONS[role];
  if (!rolePerms) return false;
  return permissions.some(p => rolePerms.has(p));
}

/**
 * 检查角色是否拥有所有指定权限。
 */
export function hasAllPermissions(role: Role, permissions: Permission[]): boolean {
  const rolePerms = ROLE_PERMISSIONS[role];
  if (!rolePerms) return false;
  return permissions.every(p => rolePerms.has(p));
}

/**
 * 检查角色层级是否达到最低要求。
 */
export function checkRoleLevel(role: Role, minRole: Role): boolean {
  return (ROLE_HIERARCHY[role] ?? 0) >= (ROLE_HIERARCHY[minRole] ?? 0);
}

/**
 * 从字符串转换为 Role 枚举。
 */
export function getRoleFromString(roleStr: string): Role {
  const normalized = roleStr.toLowerCase();
  const found = Object.values(Role).find(r => r === normalized);
  if (found) return found;
  throw new Error(`无效的角色: ${roleStr}`);
}

/**
 * 检查字符串是否为有效角色。
 */
export function isValidRole(roleStr: string): roleStr is Role {
  return Object.values(Role).includes(roleStr as Role);
}

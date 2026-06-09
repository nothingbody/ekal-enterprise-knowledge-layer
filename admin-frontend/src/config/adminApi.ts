/**
 * 默认与 deploy/nginx.conf 一致：统一部署下 /api/v1 走节点 backend，管理后台必须走中心 server 的 /api/central/v1。
 * 若本地直连中心服务且无 Nginx，可设 VITE_ADMIN_API_BASE=/api/v1。
 */
export const ADMIN_API_BASE =
  (import.meta.env.VITE_ADMIN_API_BASE as string | undefined)?.replace(/\/+$/, '') ||
  '/api/central/v1'

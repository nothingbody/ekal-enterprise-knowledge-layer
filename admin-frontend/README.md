# 知枢管理后台

中心服务器的 Web 管理面板，基于 Vue 3 + Element Plus。

## 功能页面

- **仪表板** — 用户数、设备数、Token 消耗趋势
- **用户管理** — 搜索、角色变更、禁用/启用、重置密码、删除
- **组织管理** — 创建/编辑组织、成员管理
- **设备管理** — 在线设备列表、版本分布
- **技能市场** — 审核发布、上下架
- **用量分析** — 按时间维度的 Token / 对话量趋势

## 开发

```bash
npm install
npm run dev
```

默认开发地址 `http://localhost:5173`，通过 Vite 代理转发 `/api` 到 `http://localhost:8080`。

## 构建

```bash
npm run build
```

产物输出到 `dist/` 目录，可由 Nginx 托管静态文件。

## 技术栈

- Vue 3 + TypeScript + Vite
- Element Plus + @element-plus/icons-vue
- Pinia（状态管理）
- Axios（HTTP 客户端，含 token 自动刷新）

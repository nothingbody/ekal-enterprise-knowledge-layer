# Changelog

本文件记录 RAG 数据平台各版本的重要变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。

---

## [0.1.0] - 2026-03-14

### 新增
- 统一版本号管理：backend 和 server 共享 `_version.py` 单一版本源
- CI/CD 基础工作流：GitHub Actions 自动运行后端测试、前后端构建检查
- 后台任务异常自动重启：调度器意外退出后自动重连，带指数退避
- 健康检查增强：`/api/health` 现在返回后台调度器运行状态
- LLM 错误分类：根据异常类型给出针对性的操作指引（API Key 无效、模型不存在、余额不足等）

### 变更
- **Breaking**: Backend API 路由统一为 `/api/v1/` 前缀，与 Server 保持一致
- Docker 部署支持通过 `WEB_WORKERS` 环境变量配置 Uvicorn worker 数量（默认 2）

### 安全
- Backend & Server 加密密钥派生统一升级为 HKDF（保留 SHA-256 向后兼容）
- LLM 客户端缓存 key 从 MD5 改为 SHA-256
- Docker 沙箱补充超时参数传递
- Token 黑名单改用原生异步 Redis 客户端（`redis.asyncio`），消除线程池开销
- Backend & Server token 吊销增加内存回退，Redis 不可用时仍可正常登出
- Server Refresh Token 补充已吊销检查，防止重放攻击
- `regenerate_message` 端点补充知识库访问权限校验
- Server 生产环境强制检查 SECRET_KEY 和管理员默认密码
- Backend & Server auth 限流器补充 Redis 可用性检测，确保多 Worker 共享限流计数
- 多 Worker 部署下后台调度器通过 Redis 分布式锁实现 Leader 选举，防止任务重复执行

### 修复
- auth 限流器独立于全局限流器的 Redis 检测不一致问题
- Server `get_db` 异常时未回滚事务的问题
- Backend HTTP 异常响应格式标准化为 `{status, code, detail, request_id}`
- 文档解析失败的错误信息按异常类型分类（编码、加密、损坏、超大文件），附带操作指引
- 前端文档列表失败状态增加 tooltip 展示完整错误信息

### 优化
- 重构 `lifespan` 函数：从 270 行单体拆分为 12 个职责明确的函数
- 重构 `stream_chat` 函数：提取 Agent 模式和多 Agent 模式为独立函数
- 前端 JWT 解码逻辑提取为共享工具模块，消除重复代码
- 新增核心链路集成测试骨架（认证 -> 知识库 CRUD -> Token 轮转 -> 错误格式）

---

## [0.0.6] - 初始版本

初始发布版本，包含核心 RAG 功能。

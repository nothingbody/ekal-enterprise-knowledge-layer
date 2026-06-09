# 知枢 RAG 智能知识平台

## 项目简介
知枢是一个面向企业知识管理与智能问答场景的 RAG 平台。项目围绕“文档知识入库、混合检索、智能对话、工具扩展、协作发布”构建，支持本地桌面部署与前后端分离开发模式。

平台核心目标是将分散的文档、数据库与模型能力统一纳入一个知识服务系统，帮助用户完成知识检索、问答生成、数据库查询、Agent 协作与多渠道接入。

## 核心能力

### 知识管理
- 支持 PDF、Word、Excel、PPT、Markdown、HTML、TXT、图片等多格式文档解析
- 支持固定长度、段落、递归、标题等多种切分策略
- 支持文档去重、分块编辑、向量重建、知识库导入导出
- 支持数据库数据源同步为知识片段

### 检索与问答
- 向量检索 + BM25 混合召回
- 查询改写、多查询扩展、重排序
- 流式智能问答
- 自然语言转 SQL
- 多轮上下文管理
- 用户记忆与画像注入

### Agent 与扩展
- MCP 工具接入
- Prompt 技能、技能链、自动化任务
- 多 Agent 协作问答
- 浏览器控制工具
- 沙箱代码执行
- 语音输入与 TTS 朗读

### 平台能力
- 工作空间协作
- 应用发布与分享
- 渠道接入：企业微信、钉钉、飞书、Telegram、Discord、Slack
- 系统诊断与健康检查
- Electron 桌面端封装

## 本次增强功能
当前版本已补充以下增强能力：

1. 多 Agent 协作架构  
   支持多个专业 Agent 按知识库分工协作，适用于跨知识库复杂问答。

2. 引导向导与系统诊断  
   增加交互式 SetupWizard 和系统诊断页，提升首次使用体验与排障效率。

3. 渠道生态扩展  
   新增 Discord、Slack 渠道适配器，并完善渠道配置校验。

4. 语音与工具扩展  
   支持语音输入、TTS 朗读、浏览器工具调用。

5. 安全隔离  
   支持 Docker 沙箱代码执行，并对高风险工具增加沙箱开关控制。

## 项目结构

```text
backend/         RAG 主后端（知识库、对话、渠道、技能等），支持本地/桌面部署
server/          中心服务器（组织、设备、管理后台），用于云端多租户部署
shared/          共享 Python 包（password、jwt、encryption、pagination、permissions）
shared-frontend/ 共享前端工具包（jwt、request 拦截器），供 frontend 与 admin-frontend 使用
frontend/        Vue 3 + Element Plus 用户端前端
admin-frontend/  Vue 3 + Element Plus 管理后台前端（连接 server）
desktop/         Electron 桌面端封装
doc/             项目文档与架构决策记录（ADR）
```

### 部署模式

- **桌面/本地模式**：`backend` + `frontend` + `desktop`，单机运行，无需 server
- **云端模式**：`server` + `admin-frontend` + 各节点 `backend` + `frontend`，需先部署中心服务器

## 技术架构

### 后端
- Python 3.11+
- FastAPI
- SQLAlchemy Async
- PostgreSQL / SQLite
- ChromaDB
- Celery + Redis

### 前端
- Vue 3
- TypeScript
- Vite
- Element Plus
- Pinia

### 桌面端
- Electron
- PyInstaller

## 安装与启动

### 1. 节点后端启动（本地/桌面模式）

```bash
cd backend
pip install -r requirements.txt
python desktop_main.py
```

默认会以桌面模式启动本地后端服务。

### 2. 用户端前端启动

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：
- 前端：`http://127.0.0.1:3000`
- 后端：`http://127.0.0.1:8000`

### 3. 中心服务启动（云端模式）

```bash
cd server
pip install -r requirements.txt
python run.py
```

默认开发地址：
- 中心服务：`http://127.0.0.1:8080`

### 4. 管理后台启动（云端模式）

```bash
cd admin-frontend
npm install
npm run dev
```

默认开发地址：
- 管理后台：`http://127.0.0.1:5173`

### 5. 前端构建

```bash
cd frontend
npm run build
```

如需构建管理后台：

```bash
cd admin-frontend
npm run build
```

### 6. 环境变量配置（可选）

- **frontend**：复制 `frontend/.env.example` 为 `frontend/.env`，可配置 `VITE_API_TARGET`（默认 `http://localhost:8000`）以指定开发模式下的 API 代理目标
- **admin-frontend**：复制 `admin-frontend/.env.example` 为 `admin-frontend/.env`，可配置 `VITE_API_TARGET`（默认 `http://localhost:8080`）以连接中心服务器；统一部署时可通过 `VITE_ADMIN_API_BASE=/api/central/v1` 指定管理后台 API 前缀
- **用户端**（frontend）连接 `backend`；**管理后台**（admin-frontend）连接 `server`，两者使用不同的 token（`token` / `admin_token`）

### 7. 生产环境部署（统一部署）

适用于通过 Nginx 统一暴露用户端、管理后台与 API 的场景。

#### 快速部署步骤

```bash
# 1. 配置后端/中心服务环境变量
cp deploy/.env.production.example backend/.env
# 按需为 server 配置 .env，或通过 docker compose 环境变量传入 SECRET_KEY、ADMIN_PASSWORD 等参数

# 2. 构建前端静态资源（build profile 任务需显式执行）
docker compose -f deploy/docker-compose.prod.yml --profile build run --rm frontend-build
docker compose -f deploy/docker-compose.prod.yml --profile build run --rm admin-build
docker compose -f deploy/docker-compose.prod.yml --profile build run --rm website-copy

# 3. 启动服务
docker compose -f deploy/docker-compose.prod.yml up -d
```

#### 部署架构

```
用户浏览器 → Nginx (:80)
                ├── /app/* → Frontend
                ├── /admin/* → Admin Frontend
                ├── /api/v1/* → Backend (:8000)
                └── /api/central/v1/* → Server (:8080)

Backend / Server
  ├── PostgreSQL
  ├── Redis
  └── Celery Worker（Backend）
```

#### 配置文件说明

| 文件 | 说明 |
|---|---|
| `deploy/nginx.conf` | 统一部署 Nginx 配置模板（`/api/v1` → `backend`，`/api/central/v1` → `server`） |
| `deploy/docker-compose.prod.yml` | 统一部署编排（`server` + `backend` + `celery-worker` + `nginx` + 前端构建任务） |
| `deploy/.env.production.example` | `backend` 示例环境变量模板，可作为统一部署参数参考 |

#### 前端 API 地址配置

- **统一部署（推荐）**：用户端走 `/api/v1`，管理后台走 `/api/central/v1`，分别转发到 `backend` 与 `server`
- **跨域部署**：用户端构建前设置 `VITE_API_BASE_URL=https://api.example.com`；管理后台构建前设置 `VITE_ADMIN_API_BASE=https://central.example.com/api/v1`，同时后端与中心服务的 CORS 均需包含对应前端域名

## 使用说明

### 首次使用
1. 登录系统
2. 配置 LLM 模型与 Embedding 模型
3. 创建知识库
4. 上传文档或同步数据库数据源
5. 进入智能对话页面进行问答

### 多 Agent 使用方式
1. 在“多Agent协作”页面创建 Agent
2. 为 Agent 绑定知识库和 LLM 模型
3. 在“智能对话”页面选择“多Agent”模式
4. 发起跨知识库问题，系统会自动分发并汇总回答

## 适用场景
- 企业知识库建设
- 文档智能检索与问答
- 内部制度、产品资料、研发文档统一问答
- 结构化数据库 + 非结构化文档混合查询
- 面向桌面用户的本地化知识助手

## 关键文档

### 架构决策记录 (ADR)
- `doc/adr/001-system-boundary.md`：Backend / Server 职责边界
- `doc/adr/002-database-strategy.md`：数据库与存储策略
- `doc/adr/003-api-design-conventions.md`：API 设计规范
- `doc/adr/004-vector-store-selection.md`：向量存储选型与迁移
- `doc/adr/005-workspace-data-source.md`：Workspace 数据源与同步策略

### 部署与运维
- `doc/deployment-checklist.md`：部署清单（环境变量、必填项）
- `docker-compose.full-stack.yml`：全栈 Docker Compose 示例
- `.env.example`：环境变量模板

### 质量与体验
- `doc/rag-benchmark-spec.md`：RAG 评测方案
- `doc/first-day-experience-spec.md`：首日体验优化方案
- `doc/analytics-dashboard-spec.md`：运营分析看板方案
- `data/benchmark/rag_benchmark_v1.json`：评测数据集

### 问题与改进
- `doc/架构问题分析.md`：架构问题盘点
- `doc/使用者视角问题.md`：用户体验问题盘点
- `doc/安全性审查报告.md`：安全基线与问题清单
- `doc/项目整改执行计划-周度任务分解版.md`：整改执行计划
- `doc/q1-2026-retrospective.md`：Q1 整改复盘报告
- `doc/q2-2026-roadmap.md`：Q2 季度 Roadmap

## 参与开发
欢迎基于 Issue、功能分支或 Pull Request 参与改进。

推荐流程：
1. Fork 仓库
2. 创建功能分支
3. 提交修改
4. 发起合并请求

## 许可证
当前仓库采用 MIT License，详见根目录 `LICENSE` 文件。

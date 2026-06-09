# RAG 知识库平台 — 桌面版

将 RAG 平台打包为跨平台 Electron 桌面应用，内嵌 SQLite + ChromaDB，零配置开箱即用。

## 架构

```
Electron Shell
├── BrowserWindow → 加载 http://127.0.0.1:{auto-port}
└── Python Backend (子进程)
    ├── FastAPI + Uvicorn
    ├── SQLite (内嵌数据库)
    └── ChromaDB (内嵌向量存储)
```

## 开发模式

### 前置条件
- Node.js 18+
- Python 3.10+（开发模式需系统已安装；生产版构建时会自动下载并打包）
- 已安装后端依赖：`cd ../backend && pip install -r requirements.txt`

### 运行

```bash
# 1. 构建前端
cd ../frontend && npm run build

# 2. 安装桌面依赖
cd ../desktop && npm install

# 3. 启动开发模式
npm run dev
```

开发模式下 Electron 会自动:
1. 启动 Python 后端（使用 `desktop_main.py`）
2. 等待后端就绪（健康检查）
3. 打开主窗口加载应用

### 仅测试后端

```bash
cd ../backend
python desktop_main.py
# 输出: @@PORT@@{port}@@PORT@@
# 访问: http://127.0.0.1:{port}
```

## 构建发布包

### 完整构建（推荐）

```bash
cd desktop
node build.js
```

该脚本依次执行:
1. `npm run build` — Vite 构建前端
2. `pyinstaller desktop_main.spec` — 打包后端为可执行文件
3. `electron-builder` — 打包为安装程序

### 分平台构建

```bash
npm run dist:win    # Windows (NSIS 安装包，含自动下载的 Python embeddable)
npm run dist:mac    # macOS (DMG)
npm run dist:linux  # Linux (AppImage + deb)
```

输出目录: `desktop/release/`

### Python 环境

- **开发模式**：需系统已安装 Python 3.10+；若未安装会提示并打开 python.org
- **生产构建**：`npm run build:python` 会下载 Python embeddable 到 `resources/python/`（当前仅 Windows），打包后沙箱可无需系统 Python

## 配置

桌面模式默认使用内嵌服务，无需外部依赖：

| 设置 | 桌面默认值 | 说明 |
|------|-----------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///data/rag.db` | 可切换为 PostgreSQL |
| `CHROMA_MODE` | `embedded` | 可切换为 `client` 连接外部 ChromaDB |
| `REDIS_URL` | 不需要 | 后台任务自动回退到线程模式 |
| `SANDBOX_ENABLED` | `true` | 桌面版自动启用代码执行沙箱 |
| `SANDBOX_USE_LOCAL` | `true` | 使用本地 subprocess，**无需 Docker** |
| `SANDBOX_NETWORK_DISABLED` | `false` | 允许技能脚本调用外部 API |
| `CENTRAL_SERVER_URL` | （无默认） | 中心根地址；也可只设 `SERVER_PUBLIC_IP` 由启动脚本拼成 `https://IP` |
| `SERVER_PUBLIC_IP` | （无） | 公网 IP，与 `CENTRAL_SERVER_SCHEME`（默认 `https`）拼成中心 URL |
| `CENTRAL_API_PREFIX` | 见下 | 经统一 Nginx 部署时**必须**为 `/api/central/v1`，否则 `/api/v1` 会打到节点后端而非中心服 |

用户数据目录下可复制 `central.json.example` 为 `central.json`，填写 `server_public_ip`（或 `central_server_url`），Electron 会注入子进程环境变量。

公网 IP/域名与 `deploy/nginx.conf` 一致时：中心 API 前缀为 `/api/central/v1`；仅当 `CENTRAL_SERVER_URL` 指向本机 `127.0.0.1` / `localhost` 直连中心进程时，才使用 `/api/v1`。

如需连接外部 PostgreSQL，在 `backend/.env` 中设置：
```
DATABASE_URL=postgresql+asyncpg://user:<password>@host:5432/dbname
```

## 数据位置

- 数据库: `backend/data/rag.db`
- 向量存储: `backend/data/chroma/`
- 上传文件: `backend/uploads/`
- 密钥: `backend/data/.secret_key`

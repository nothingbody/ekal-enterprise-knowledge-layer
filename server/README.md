# 知枢中心服务器

桌面端 + 中心服务器架构中的中心服务端，负责统一认证、技能市场、设备管理和用量统计。

## 快速启动

### Docker Compose（推荐）

```bash
# 1. 先构建前端
docker compose --profile build run --rm admin-build

# 2. 启动所有服务
docker compose up -d
```

服务启动后：
- 管理后台：`http://localhost`（Nginx）
- API 文档：`http://localhost/docs`（需 DEBUG=true）
- 默认管理员：`admin` / `.env 中的 ADMIN_PASSWORD`（首次登录后请立即修改密码）

### 本地开发

```bash
# 1. 启动 PostgreSQL 和 Redis（可用 docker compose 只启动依赖）
docker compose up -d postgres redis

# 2. 创建 .env
cp .env.example .env
# 编辑 .env 设置 DEBUG=true

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动
python run.py
```

API 地址：`http://localhost:8080`

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL 连接串 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `SECRET_KEY` | — | JWT 签名密钥（生产必改） |
| `ADMIN_EMAIL` | `admin@example.com` | 默认管理员邮箱 |
| `ADMIN_PASSWORD` | required | 默认管理员密码 |
| `ALLOW_REGISTRATION` | `true` | 是否允许注册 |
| `CORS_ORIGINS` | `http://localhost` | 允许的 CORS 源 |
| `DEBUG` | `false` | 调试模式（开启 Swagger） |

## API 模块

| 路径前缀 | 功能 |
|----------|------|
| `/api/auth` | 注册、登录、刷新 token |
| `/api/users` | 用户 CRUD、重置密码 |
| `/api/organizations` | 组织 CRUD、成员管理 |
| `/api/devices` | 设备注册、心跳、列表 |
| `/api/stats` | 用量上报、趋势查询 |
| `/api/skills` | 技能市场、发布、审核 |
| `/api/admin` | 仪表板聚合数据 |

## 项目结构

```
server/
├── app/
│   ├── api/          # API 路由
│   ├── core/         # 安全、加密
│   ├── models/       # SQLAlchemy 数据模型
│   ├── config.py     # 配置（pydantic-settings）
│   ├── database.py   # 数据库引擎
│   ├── main.py       # FastAPI 应用入口
│   └── schemas.py    # Pydantic schema
├── docker-compose.yml
├── Dockerfile
├── nginx.conf
├── requirements.txt
└── run.py
```

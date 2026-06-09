# 知枢 RAG 平台 — ADR-002 数据库与存储策略

> 目的：明确 Backend 与 Server 的数据库隔离策略、Migration 管理规范与向量存储选型指南。

---

## 一、状态

- **状态**：Accepted
- **生效日期**：2026-03-29
- **适用范围**：`backend`、`server`

---

## 二、背景

当前仓库存在两套独立的数据库配置与 Migration：

- **Backend**：支持 SQLite（桌面/本地模式）与 PostgreSQL（生产模式）
- **Server**：仅支持 PostgreSQL

两套 Migration 相互独立，若部署时共享同一 PostgreSQL 实例，可能产生表名冲突或外键依赖问题。此外，向量存储（ChromaDB vs PgVector）的选型与迁移路径尚未明确。

---

## 三、决策

### 3.1 数据库隔离策略

**Backend 与 Server 使用独立数据库实例或 Schema**，不共享同一命名空间。

| 部署模式 | Backend 数据库 | Server 数据库 | 说明 |
|----------|----------------|---------------|------|
| 桌面/本地 | SQLite（本地文件） | 无 | 单机运行，无 Server |
| 云端单机 | PostgreSQL `rag_backend` | PostgreSQL `rag_server` | 同一 PG 实例，不同 database |
| 云端集群 | PostgreSQL（专用实例） | PostgreSQL（专用实例） | 完全隔离 |

### 3.2 Migration 管理规范

1. **独立 Alembic 环境**：Backend 与 Server 各自维护独立的 `alembic/` 目录与版本历史
2. **表名前缀约定**：
   - Backend 表名：无前缀（如 `users`, `knowledge_bases`, `documents`）
   - Server 表名：无前缀（如 `users`, `organizations`, `devices`）
3. **禁止跨服务外键**：Backend 与 Server 的表之间不得建立外键约束
4. **Migration 顺序**：部署时先执行 Server migration，再执行 Backend migration

### 3.3 SQLite 与 PostgreSQL 兼容性

1. **JSON 字段**：使用 `sa.JSON` 而非 `sa.dialects.postgresql.JSONB`
2. **自增主键**：使用 `sa.BigInteger().with_variant(sa.Integer, 'sqlite')`
3. **时间戳**：使用 `sa.DateTime(timezone=True)` 而非 PG 专用类型
4. **文本搜索**：SQLite 模式下降级为 `LIKE` 查询，PG 模式使用全文搜索

### 3.4 向量存储选型

| 场景 | 推荐存储 | 说明 |
|------|----------|------|
| 桌面/本地/小规模 | ChromaDB | 嵌入式，无需额外服务，适合 <10 万向量 |
| 中大规模/生产 | PgVector | 与 PostgreSQL 集成，支持 HNSW 索引，适合 10-1000 万向量 |
| 超大规模 | 专用向量数据库 | Milvus/Qdrant/Pinecone，需评估后决定 |

### 3.5 ChromaDB 配置规范

1. **持久化路径**：`DATA_DIR/chromadb/`，与 SQLite 数据目录同级
2. **备份策略**：定期备份 `persist_directory` 目录
3. **迁移路径**：提供 ChromaDB → PgVector 迁移脚本（待实现）

---

## 四、实施规则

### 4.1 新增 Migration 规范

1. 每个 Migration 必须包含 `upgrade()` 和 `downgrade()` 函数
2. 涉及数据迁移的 Migration 必须分两步：先 DDL，再 DML
3. 禁止在 Migration 中硬编码数据库方言特定语法

### 4.2 部署检查清单

部署前确认：

- [ ] Backend 与 Server 数据库连接字符串指向不同 database
- [ ] 两套 Migration 均已执行到最新版本
- [ ] 向量存储配置与数据目录权限正确
- [ ] Redis 连接（如使用）配置正确

### 4.3 数据同步策略

Backend 与 Server 之间的数据同步通过 API 调用实现，不通过数据库层面直接访问：

- **用户同步**：Server 为权威源，Backend 通过 Auth Bridge 验证
- **工作空间同步**：Server 持有组织级视图，Backend 持有节点本地数据
- **技能同步**：Server 技能市场为源，Backend 安装本地副本

---

## 五、环境变量配置示例

### Backend (.env)

```bash
# SQLite（本地/桌面）
DATABASE_URL=sqlite+aiosqlite:///./data/rag.db

# PostgreSQL（生产）
DATABASE_URL=postgresql+asyncpg://user:<password>@localhost:5432/rag_backend

# 向量存储
VECTOR_STORE_TYPE=chromadb  # 或 pgvector
CHROMADB_PERSIST_DIR=./data/chromadb
```

### Server (.env)

```bash
DATABASE_URL=postgresql+asyncpg://user:<password>@localhost:5432/rag_server
REDIS_URL=redis://localhost:6379/0
```

---

## 六、不在本 ADR 内解决的事项

- ChromaDB → PgVector 自动迁移工具实现
- 超大规模向量存储（Milvus/Qdrant）集成
- 多租户 Schema 隔离方案
- 数据库读写分离与连接池优化

---

*ADR 版本：1.0 | 生效日期：2026-03-29*

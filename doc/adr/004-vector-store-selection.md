# ADR-004: 向量存储选型与迁移策略

> 状态：已采纳  
> 日期：2026-03-29  
> 决策者：架构组

---

## 背景

知枢 RAG 平台需要高效的向量存储来支持语义检索。当前支持两种向量存储：
- **ChromaDB**：轻量级嵌入式向量数据库
- **PgVector**：PostgreSQL 向量扩展

需要明确各存储的适用场景、性能边界和迁移路径。

---

## 决策

### 选型建议

| 场景 | 推荐存储 | 理由 |
|------|----------|------|
| 桌面模式 / 开发测试 | ChromaDB | 零配置、嵌入式、启动快 |
| 文档数 < 10 万 | ChromaDB | 性能足够、运维简单 |
| 文档数 10-100 万 | PgVector | 更好的并发和索引支持 |
| 文档数 > 100 万 | PgVector + 分片 | 考虑水平扩展方案 |
| 生产环境 / 多节点 | PgVector | 集中存储、便于备份 |

### ChromaDB 配置

```python
# 嵌入式模式（桌面/单机）
VECTOR_STORE_TYPE=chroma
CHROMA_MODE=embedded
CHROMA_DATA_DIR=/app/data/chroma

# HTTP 模式（多 Worker）
VECTOR_STORE_TYPE=chroma
CHROMA_MODE=http
CHROMA_HOST=localhost
CHROMA_PORT=8100
```

**持久化目录**：
- 桌面模式：`$DESKTOP_DATA_DIR/chroma`
- 服务模式：`./data/chroma`

**备份策略**：
```bash
# 停止服务后直接复制目录
cp -r /app/data/chroma /backup/chroma-$(date +%Y%m%d)
```

### PgVector 配置

```python
VECTOR_STORE_TYPE=pgvector
DATABASE_URL=postgresql+asyncpg://user:<password>@localhost:5432/rag
```

**索引建议**：
```sql
-- 对于 100 万以下文档，使用 IVFFlat
CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 对于更大规模，使用 HNSW
CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops);
```

---

## 性能参考

### ChromaDB

| 文档数 | 查询延迟 (P95) | 内存占用 | 备注 |
|--------|---------------|----------|------|
| 1 万 | < 50ms | ~500MB | 推荐 |
| 10 万 | < 200ms | ~2GB | 可接受 |
| 50 万 | < 1s | ~8GB | 边界 |
| 100 万+ | 不推荐 | - | 迁移到 PgVector |

### PgVector

| 文档数 | 查询延迟 (P95) | 索引类型 | 备注 |
|--------|---------------|----------|------|
| 10 万 | < 30ms | IVFFlat | 推荐 |
| 100 万 | < 100ms | HNSW | 推荐 |
| 1000 万+ | < 200ms | HNSW + 分区 | 需要调优 |

---

## 迁移路径

### ChromaDB → PgVector

```python
# 1. 导出 ChromaDB 数据
from backend.app.services.vector_store import get_vector_store

chroma_store = get_vector_store("chroma")
documents = chroma_store.export_all()

# 2. 配置切换
VECTOR_STORE_TYPE=pgvector

# 3. 导入 PgVector
pg_store = get_vector_store("pgvector")
pg_store.import_all(documents)

# 4. 验证
assert pg_store.count() == len(documents)
```

### 回滚策略

1. 保留原 ChromaDB 数据目录至少 7 天
2. 迁移后对比检索结果一致性
3. 监控查询延迟和准确率

---

## 监控指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| `vector_query_latency_seconds` | 检索延迟 | P95 > 1s |
| `vector_store_document_count` | 文档总数 | 接近容量边界 |
| `vector_store_memory_bytes` | 内存占用 | > 80% 可用内存 |

---

## 后续规划

1. **短期**：完善 PgVector 索引自动创建逻辑
2. **中期**：添加向量存储健康检查端点
3. **长期**：评估 Milvus、Qdrant 等专业向量数据库

---

## 参考

- [ChromaDB 文档](https://docs.trychroma.com/)
- [PgVector 文档](https://github.com/pgvector/pgvector)
- [向量索引选型指南](https://ann-benchmarks.com/)

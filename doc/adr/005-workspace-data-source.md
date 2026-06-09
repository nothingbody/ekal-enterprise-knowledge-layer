# ADR-005: Workspace 数据源与同步策略

> 状态：已采纳  
> 日期：2026-03-29  
> 决策者：架构组

---

## 背景

知枢平台支持两种部署模式：
- **桌面模式**：Backend 单独运行，无 Server
- **云端模式**：Server + 多个 Backend 节点

Workspace 在两种模式下的数据源和同步策略需要明确。

---

## 决策

### Workspace 主数据源

| 部署模式 | 主数据源 | 说明 |
|----------|----------|------|
| 桌面模式 | Backend 本地 | Workspace 在 Backend SQLite 中创建和管理 |
| 云端模式 | Server | Workspace 由 Server 创建，同步到各 Backend |

### 数据流向

#### 桌面模式

```
用户 → Backend → 本地 SQLite
                     ↓
              Workspace 表
```

- Workspace 完全由 Backend 管理
- 无需与 Server 同步
- `workspace_id` 由本地生成（UUID）

#### 云端模式

```
管理员 → Server → PostgreSQL (主)
                      ↓
                Workspace 表
                      ↓
            同步到各 Backend 节点
                      ↓
              Backend SQLite/PG (从)
```

- Server 是 Workspace 的权威来源
- Backend 定期从 Server 拉取 Workspace 列表
- Backend 本地缓存 Workspace 信息以支持离线

### 同步机制

#### Backend 启动时同步

```python
# backend/app/cloud/workspace_sync.py
async def sync_workspaces_from_server():
    """从 Server 同步 Workspace 列表到本地。"""
    if not settings.CENTRAL_SERVER_URL:
        return  # 桌面模式，跳过
    
    try:
        workspaces = await fetch_workspaces_from_server()
        await upsert_local_workspaces(workspaces)
    except Exception as e:
        logger.warning("Workspace 同步失败，使用本地缓存: %s", e)
```

#### 定期增量同步

```python
# 每 5 分钟检查更新
WORKSPACE_SYNC_INTERVAL = 300

async def periodic_workspace_sync():
    while True:
        await asyncio.sleep(WORKSPACE_SYNC_INTERVAL)
        await sync_workspaces_from_server()
```

### Redis Key 命名规范

为避免跨租户数据泄露，所有缓存 key 必须包含 workspace 前缀：

```
# 格式
rag:{workspace_id}:{resource_type}:{resource_id}

# 示例
rag:ws_abc123:chat:session_456
rag:ws_abc123:retrieval:cache_789
rag:ws_abc123:token_blacklist:jti_xxx
```

#### 实现

```python
# shared/rag_platform_common/cache_keys.py
def cache_key(workspace_id: str, resource_type: str, resource_id: str) -> str:
    """生成带 workspace 前缀的缓存 key。"""
    return f"rag:{workspace_id}:{resource_type}:{resource_id}"

def chat_session_key(workspace_id: str, session_id: str) -> str:
    return cache_key(workspace_id, "chat", session_id)

def retrieval_cache_key(workspace_id: str, query_hash: str) -> str:
    return cache_key(workspace_id, "retrieval", query_hash)
```

---

## 数据隔离检查清单

### Backend 侧

- [ ] 所有数据库查询包含 `workspace_id` 过滤
- [ ] 所有 Redis 操作使用带 workspace 前缀的 key
- [ ] 文件上传路径包含 workspace 隔离目录
- [ ] 向量存储按 workspace 分 collection

### Server 侧

- [ ] Organization 下可创建多个 Workspace
- [ ] Workspace 成员权限独立管理
- [ ] 跨 Workspace 数据访问需显式授权

---

## 冲突处理

### Workspace 不存在

当 Backend 收到请求但本地无对应 Workspace 时：

1. 云端模式：向 Server 查询，若存在则同步并处理
2. 桌面模式：返回 404 错误

### Workspace 被删除

1. Server 标记 Workspace 为 `deleted`
2. Backend 同步时检测到删除标记
3. Backend 清理本地相关数据（异步）
4. 清理对应的 Redis 缓存

---

## 后续规划

1. **短期**：实现 workspace 同步接口
2. **中期**：添加 workspace 级别的配额限制
3. **长期**：支持跨 workspace 数据共享（需显式授权）

---

## 参考

- ADR-001: Backend/Server 职责边界
- ADR-002: 数据库与存储策略

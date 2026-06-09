# 知枢 RAG 平台 — ADR-003 API 设计规范

> 目的：统一 Backend 与 Server 的 API 设计约定，包括分页、筛选、响应格式与版本策略。

---

## 一、状态

- **状态**：Accepted
- **生效日期**：2026-03-29
- **适用范围**：`backend/app/api/*`、`server/app/api/*`

---

## 二、背景

当前 API 存在以下不一致：

1. **分页参数**：部分接口用 `page`/`page_size`，部分用 `skip`/`limit`
2. **搜索参数**：有 `search`、`keyword`、`q` 等多种命名
3. **响应格式**：成功用 `message`，错误用 `detail`，缺乏统一结构
4. **版本策略**：仅路径前缀 `/api/v1/`，无字段废弃规范

---

## 三、决策

### 3.1 分页参数

**统一使用 `page` + `page_size`**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码，从 1 开始 |
| `page_size` | int | 20 | 每页条数，最大 100 |

**响应格式**：

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "pages": 5
}
```

**示例**：

```python
@router.get("/items")
async def list_items(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    offset = (page - 1) * page_size
    items = await db.execute(select(Item).offset(offset).limit(page_size))
    total = await db.scalar(select(func.count()).select_from(Item))
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }
```

### 3.2 搜索与筛选参数

**统一使用 `keyword` 作为全文搜索参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `keyword` | str | 全文搜索关键词（模糊匹配） |
| `status` | str/enum | 状态筛选 |
| `type` | str/enum | 类型筛选 |
| `created_after` | datetime | 创建时间下限 |
| `created_before` | datetime | 创建时间上限 |
| `sort_by` | str | 排序字段 |
| `sort_order` | str | 排序方向：`asc` / `desc` |

**示例**：

```python
@router.get("/documents")
async def list_documents(
    keyword: str = Query(None, description="搜索关键词"),
    status: str = Query(None, description="状态筛选"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
):
    ...
```

### 3.3 响应格式

#### 成功响应

**单对象**：

```json
{
  "id": 1,
  "name": "example",
  ...
}
```

**列表（分页）**：

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "pages": 5
}
```

**操作结果**：

```json
{
  "message": "操作成功",
  "data": { ... }  // 可选
}
```

#### 错误响应

**统一使用 `detail` 字段**：

```json
{
  "detail": "错误描述"
}
```

**验证错误（422）**：

```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 3.4 版本策略

1. **路径前缀**：所有 API 使用 `/api/v1/` 前缀
2. **字段废弃**：
   - 废弃字段保留至少 2 个版本周期（约 6 个月）
   - 废弃字段添加 `deprecated` 文档说明
   - 响应中废弃字段设置为 `null` 或移除前发出警告
3. **重大变更**：需提升主版本号（如 `/api/v2/`）

### 3.5 命名约定

| 场景 | 约定 | 示例 |
|------|------|------|
| 路径 | 小写复数名词 + kebab-case | `/knowledge-bases`, `/api-keys` |
| 查询参数 | snake_case | `page_size`, `sort_by` |
| 请求/响应字段 | snake_case | `created_at`, `user_id` |
| 枚举值 | snake_case | `in_progress`, `completed` |

---

## 四、实施规则

### 4.1 新增 API 检查清单

- [ ] 使用 `page` + `page_size` 分页参数
- [ ] 搜索参数使用 `keyword`
- [ ] 响应包含 `total`, `page`, `page_size`, `pages`
- [ ] 错误使用 `detail` 字段
- [ ] 路径使用 kebab-case 复数名词
- [ ] 添加 OpenAPI 文档描述

### 4.2 已有 API 迁移

优先级按使用频率排序：

1. **高频接口**：`/chat/*`, `/knowledge-bases/*`, `/documents/*`
2. **中频接口**：`/users/*`, `/models/*`, `/workspaces/*`
3. **低频接口**：其他管理类接口

迁移时保持向后兼容：
- 同时支持旧参数名（如 `skip`）和新参数名（如 `page`）
- 旧参数标记为 deprecated
- 下一主版本移除旧参数

---

## 五、共享工具

在 `shared/` 或各服务的 `app/core/` 中提供分页工具：

```python
# shared/rag_platform_common/pagination.py

from typing import TypeVar, Generic, List
from pydantic import BaseModel

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int

def paginate(
    items: List[T],
    total: int,
    page: int,
    page_size: int,
) -> PaginatedResponse[T]:
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size if page_size > 0 else 0,
    )
```

---

## 六、不在本 ADR 内解决的事项

- API 网关层的统一限流与认证
- GraphQL 或 gRPC 替代方案
- API 文档自动生成与发布

---

*ADR 版本：1.0 | 生效日期：2026-03-29*

# 知枢 RAG 平台 — ADR-001 Backend 与 Server 职责边界

> 目的：冻结 `backend` 与 `server` 的职责边界，降低架构漂移、重复实现与部署认知混乱。

---

## 一、状态

- **状态**：Accepted
- **生效日期**：2026-03-29
- **适用范围**：`backend`、`server`、`frontend`、`admin-frontend`、`shared`

---

## 二、背景

当前仓库已经形成双后端、双前端、多部署模式并存的结构：

- `backend`：RAG 主后端，承载知识库、文档处理、检索、对话、数据库问答、工具调用、技能、Agent、多渠道等运行时能力。
- `server`：中心服务器，承载统一认证、组织与设备管理、技能市场、后台配置、统计与管理后台能力。
- `frontend`：用户端前端，主要面向知识库、对话、模型、渠道、工作空间等业务操作。
- `admin-frontend`：管理后台，主要面向组织、用户、设备、统计、平台配置等中心化管理能力。

随着功能演进，`backend` 与 `server` 在认证、工作空间、知识库、聊天等概念上出现边界重叠风险。若不明确主从关系，会带来以下问题：

1. 新增功能时无法明确归属，重复实现增多。
2. 文档与部署路径容易出现不一致。
3. 前端需要依赖“约定俗成”判断请求打向哪个服务。
4. 安全、配置、权限等基础能力持续双端平行演进，维护成本上升。

---

## 三、当前仓库事实（以代码与配置为准）

### 3.1 API 路由与前端访问关系

- `frontend` 主要面向 `backend`，默认走 `/api/v1/*`。
- `admin-frontend` 面向 `server`，统一部署时默认走 `/api/central/v1/*`。
- `server/docker-compose.yml` 中，管理后台静态资源并非由 `docker compose up -d --build` 自动生成，而是通过 `admin-build` profile 任务输出到 `admin_dist`。
- `deploy/docker-compose.prod.yml` 中，统一部署场景同时包含 `server`、`backend`、`celery-worker`、`nginx`，以及 `admin-build`、`frontend-build`、`website-copy` 等构建任务。

### 3.2 运行模式事实

- 截至本 ADR 生效时，`backend/desktop_main.py` 的当前仓库代码仍会本地启动 Python 后端，用于桌面/本地模式。
- 因此，任何关于桌面运行方式的判断，都必须以当前仓库代码为准；若未来改为 remote-only desktop，应通过新的 ADR 与 README 更新统一冻结。

### 3.3 测试与治理事实

- 当前 CI 已覆盖 `backend` 测试与前端构建，但 `server` 仍主要停留在导入检查，尚未形成与 `backend` 对等的自动化测试门禁。
- 当前根目录已有 `LICENSE`，但根 README 仍存在过时表述，说明文档更新机制尚未完全跟上代码演进。

---

## 四、决策

### 4.1 总体原则

系统分为两类平面：

- **控制平面（Control Plane）**：由 `server` 负责。
- **运行平面（Runtime Plane）**：由 `backend` 负责。

### 4.2 `server` 的职责

`server` 是中心控制平面，负责：

- 统一认证与中心账户体系
- 组织、用户、设备管理
- 审计、统计、通知、后台配置
- 技能市场与平台级发布管理
- 管理后台所需的聚合视图与中心配置能力

`server` **不应成为重度 RAG 运行时的主执行面**。除非明确说明为聚合、代理或中心元数据能力，否则不应在 `server` 中重复实现 `backend` 的知识检索、文档处理与对话运行时能力。

### 4.3 `backend` 的职责

`backend` 是节点运行平面，负责：

- 知识库、文档上传、解析、切分、Embedding
- 检索、重排序、上下文构建
- 对话、流式回答、NL2SQL、Agent、多 Agent
- MCP、自动化、技能执行、多渠道接入
- 文档处理任务、异步运行时、节点内业务计算

`backend` 是所有 RAG 主链路与业务运行时的主执行服务。

### 4.4 `frontend` 与 `admin-frontend` 的职责

- `frontend` 面向普通业务用户，主要访问 `backend`。
- `admin-frontend` 面向平台或组织管理者，主要访问 `server`。
- 若某项功能既有业务端视角又有中心管理视角，必须在接口归属上明确“主服务”与“聚合服务”，禁止双端长期平行复制。

---

## 五、领域归属矩阵

| 领域 | 主归属服务 | 辅助/桥接服务 | 说明 |
|---|---|---|---|
| 用户登录与中心认证 | `server` | `backend` 可在云模式下做受控代理/桥接 | 中心认证应由 `server` 作为权威来源 |
| 本地/节点用户会话 | `backend` | `server` | 仅限节点本地运行模式；云模式以中心认证为准 |
| 组织、设备、审计、通知 | `server` | 无 | 控制平面专属职责 |
| 平台配置、运营统计、技能市场 | `server` | `backend` 可消费 | 中心化管理职责 |
| 知识库元数据与文档处理 | `backend` | `server` 可做聚合展示 | 实际索引、切片、Embedding 在 `backend` |
| 检索与对话 | `backend` | `server` 不应重度复刻 | RAG 运行时主链路归 `backend` |
| 工作空间业务数据 | `backend` | `server` 可持有中心级管理视图 | 若涉及中心同步，需显式定义主数据源 |
| 管理后台页面数据 | `server` | `backend` 提供节点数据 | `admin-frontend` 默认访问 `server` |
| 用户业务前端页面数据 | `backend` | `server` 仅在必要时桥接 | `frontend` 默认访问 `backend` |

---

## 六、实施规则

### 6.1 接口归属规则

1. 所有新增接口必须先声明主归属服务。
2. 若 `server` 仅为了统一入口或中心化视图访问某项 `backend` 能力，必须明确标注为：
   - 代理
   - 聚合
   - 元数据同步
3. 禁止在 `server` 与 `backend` 中长期保留语义相同、实现独立、缺乏主从关系说明的双份业务接口。

### 6.2 前端接入规则

1. `frontend` 默认访问 `backend`。
2. `admin-frontend` 默认访问 `server`。
3. 若统一部署走 Nginx：
   - `/api/v1/*` → `backend`
   - `/api/central/v1/*` → `server`
4. 若本地开发直连服务，可由各前端的 dev proxy 指向对应服务，但接口归属不变。

### 6.3 共享能力规则

以下能力优先沉淀到 `shared/` 或等效公共层：

- 权限与角色常量
- Token 与认证辅助工具
- 配置辅助工具
- 通用错误结构约定
- 可复用的安全基础能力

### 6.4 文档与部署规则

1. 任何改变接口归属、路由前缀、部署入口的改动，必须同步更新：
   - 根 `README.md`
   - 对应子模块 README
   - 部署说明
   - ADR
2. 管理后台构建任务的变化必须在根 README 与 `server/README.md` 中同步说明。

---

## 七、不在本 ADR 内解决的事项

以下事项属于后续整改范围，但不在本 ADR 中直接定实现方案：

- `backend` 与 `server` 的加密实现统一路径
- 工作空间主数据源的最终长期方案
- remote-only desktop 的最终产品形态
- 多租户隔离的 Redis key、数据库命名空间与规模化策略

这些事项如发生结构性变化，应以新的 ADR 继续冻结。

---

## 八、后续动作

根据本 ADR，优先执行以下整改项：

1. 拆分 `backend/app/main.py` 与 `backend/app/services/chat_service.py`
2. 将 `server` 测试接入 CI，替代仅导入检查
3. 修正根 README 中的 License、部署与管理后台构建说明
4. 建立双前端共享层与统一权限常量

---

*ADR 版本：1.0 | 生效日期：2026-03-29*

# 贡献指南

感谢您对知枢 RAG 平台的关注！本文档将帮助您了解如何参与项目贡献。

---

## 快速开始

### 1. Fork & Clone

```bash
git clone https://github.com/YOUR_USERNAME/rag-platform.git
cd rag-platform
```

### 2. 环境搭建

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 3. 运行测试

```bash
# Backend
cd backend
pytest tests/ -v

# Frontend
cd frontend
npm run build
```

---

## 贡献流程

### 提交 Issue

在提交代码前，建议先创建 Issue 讨论：

1. **Bug 报告** — 使用 Bug Report 模板
2. **功能请求** — 使用 Feature Request 模板
3. **问题咨询** — 使用 Question 模板

### 提交 PR

1. 基于 `develop` 分支创建特性分支
2. 提交前确保测试通过
3. 填写 PR 模板
4. 等待 Code Review

```bash
git checkout -b feature/your-feature develop
# 开发...
git commit -m "feat: add your feature"
git push origin feature/your-feature
```

---

## 代码规范

### Python (Backend/Server)

- 格式化：`black` + `isort`
- 类型检查：`mypy`
- 代码检查：`ruff`

```bash
black app/
isort app/
ruff check app/
```

### TypeScript (Frontend)

- 格式化：`prettier`
- 代码检查：`eslint`

```bash
npm run lint
npm run format
```

### Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type**:
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建/工具

**示例**:
```
feat(chat): add streaming response support

- Implement SSE for real-time response
- Add abort controller for cancellation

Closes #123
```

---

## 项目结构

```
rag-platform/
├── backend/          # RAG 主后端 (FastAPI)
├── server/           # 中心服务器 (FastAPI)
├── shared/           # Python 共享包
├── frontend/         # 用户端 (Vue 3)
├── admin-frontend/   # 管理后台 (Vue 3)
├── shared-frontend/  # 前端共享包
├── desktop/          # 桌面端 (Electron)
├── doc/              # 文档
└── data/             # 数据文件
```

---

## 开发指南

### 添加新 API

1. 在 `backend/app/api/` 创建路由模块
2. 在 `backend/app/app_routes.py` 注册路由
3. 添加测试到 `backend/tests/`
4. 更新 API 文档

### 添加新组件

1. 在 `frontend/src/components/` 创建组件
2. 遵循 Vue 3 Composition API
3. 使用 Element Plus 组件库
4. 添加类型定义

### 添加共享功能

1. 评估是否适合放入 `shared/` 或 `shared-frontend/`
2. 确保向后兼容
3. 更新导出列表
4. 添加单元测试

---

## 测试要求

### 必需测试

- 新 API 端点必须有测试
- Bug 修复必须有回归测试
- 核心功能变更需要集成测试

### 运行测试

```bash
# Backend 全量测试
cd backend && pytest tests/ -v

# Server 测试
cd server && pytest tests/ -v

# 前端构建验证
cd frontend && npm run build
cd admin-frontend && npm run build
```

---

## Code Review 检查清单

- [ ] 代码符合规范
- [ ] 测试通过
- [ ] 文档已更新
- [ ] 无安全问题
- [ ] 无性能问题
- [ ] 向后兼容

---

## 社区

- **Issues**: 问题和功能请求
- **Discussions**: 一般讨论
- **Pull Requests**: 代码贡献

---

## 许可证

本项目采用 [MIT License](LICENSE)。提交贡献即表示您同意将代码以相同许可证发布。

---

感谢您的贡献！🎉

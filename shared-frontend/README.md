# @rag-platform/shared-utils

知枢 RAG 平台前端共享工具库，提供 `frontend` 和 `admin-frontend` 共用的基础能力。

## 功能

### JWT 工具 (`jwt.ts`)

- `decodeJwtPayload(token)` - 解码 JWT payload（不验证签名）
- `isTokenExpired(token, bufferMs?)` - 检查 token 是否过期
- `getUserIdFromToken(token)` - 提取用户 ID
- `getRoleFromToken(token)` - 提取用户角色

### 请求工具 (`request.ts`)

- `formatErrorDetail(detail)` - 格式化 API 错误详情
- `createRequestInterceptor(options)` - 创建请求拦截器（注入 token）
- `createResponseInterceptorFactory(instance, options)` - 创建响应拦截器（自动刷新 token）
- `createLocalStorageTokens(keys)` - 创建 localStorage token 存储

## 使用方式

### 在 frontend 或 admin-frontend 中引用

1. 在 `package.json` 中添加依赖：

```json
{
  "dependencies": {
    "@rag-platform/shared-utils": "file:../shared-frontend"
  }
}
```

2. 导入使用：

```typescript
import { isTokenExpired, formatErrorDetail } from '@rag-platform/shared-utils'
```

## 开发

```bash
cd shared-frontend
npm install
npm run build
```

## 目录结构

```
shared-frontend/
├── src/
│   ├── index.ts      # 主入口
│   ├── jwt.ts        # JWT 工具
│   └── request.ts    # 请求工具
├── package.json
├── tsconfig.json
└── README.md
```

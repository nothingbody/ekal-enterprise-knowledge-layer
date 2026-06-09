# rag-platform-common

知枢 RAG 平台共享库，供 Backend 与 Server 共同使用。

## 安装

在 Backend 和 Server 目录下执行：

```bash
pip install -e ../shared
```

或在根目录 `requirements-shared.txt` 中引用。

## 模块

### 密码与认证

- **password**: `hash_password`, `verify_password`（兼容 bcrypt 与 PBKDF2 旧格式）
- **jwt_utils**: `create_access_token`, `create_refresh_token`（参数化，不依赖 app.config）
- **token_blacklist**: `revoke_token`, `is_token_revoked`（支持 Redis + 内存回退）

### 加密

- **encryption**: `encrypt_value`, `decrypt_value`, `is_encrypted`, `migrate_to_fernet`
  - 统一使用 Fernet 加密
  - 兼容 Backend 历史 AES-256-CBC 数据解密
  - 支持 HKDF 和 legacy SHA-256 密钥派生

### 分页

- **pagination**: `paginate`, `calculate_offset`, `validate_pagination`, `PaginatedResult`

### 权限

- **permissions**: `Role`, `Permission`, `has_permission`, `check_role_level`
  - 角色枚举：`SUPER_ADMIN`, `ADMIN`, `ORG_ADMIN`, `USER`, `VIEWER`, `GUEST`
  - 权限枚举：`KB_READ`, `KB_WRITE`, `DOC_READ`, `CHAT_WRITE` 等
  - 角色层级与权限映射

## 使用示例

### 密码哈希

```python
from rag_platform_common import hash_password, verify_password

hashed = hash_password("mypassword")
ok = verify_password("mypassword", hashed)
```

### JWT Token

```python
from rag_platform_common.jwt_utils import create_access_token, create_refresh_token
from app.config import settings

access = create_access_token(
    {"sub": str(user_id)},
    secret_key=settings.SECRET_KEY,
    algorithm=settings.ALGORITHM,
    default_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
)
```

### 加密

```python
from rag_platform_common import encrypt_value, decrypt_value

encrypted = encrypt_value("api-key-secret", settings.SECRET_KEY)
decrypted = decrypt_value(encrypted, settings.SECRET_KEY)
```

### 分页

```python
from rag_platform_common import paginate, calculate_offset

offset = calculate_offset(page=2, page_size=20)  # 20
result = paginate(items=data, total=100, page=2, page_size=20)
# result.to_dict() → {"items": [...], "total": 100, "page": 2, "page_size": 20, "pages": 5}
```

### 权限检查

```python
from rag_platform_common import Role, Permission, has_permission, check_role_level

if has_permission(Role.USER, Permission.KB_WRITE):
    # 允许写入知识库
    pass

if check_role_level(user.role, Role.ORG_ADMIN):
    # 用户角色至少是组织管理员
    pass
```

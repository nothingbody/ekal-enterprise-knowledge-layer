#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$SCRIPT_DIR"

echo "═══════════════════════════════════════"
echo "  知枢 RAG 平台 — 生产部署"
echo "═══════════════════════════════════════"

# ── 检查 Docker ──
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose V2 未安装"
    exit 1
fi

echo "✅ Docker $(docker --version | grep -oP '\d+\.\d+\.\d+')"
echo "✅ $(docker compose version)"

# ── 创建 .env ──
if [ ! -f .env ]; then
    echo ""
    echo "📝 创建环境配置文件..."
    cp .env.example .env

    SERVER_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))" 2>/dev/null || openssl rand -base64 48)
    BACKEND_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))" 2>/dev/null || openssl rand -base64 48)
    DB_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))" 2>/dev/null || openssl rand -base64 18)

    sed -i "s|REPLACE_WITH_RANDOM_SERVER_SECRET|${SERVER_KEY}|g" .env
    sed -i "s|REPLACE_WITH_RANDOM_BACKEND_SECRET|${BACKEND_KEY}|g" .env
    sed -i "s|REPLACE_WITH_STRONG_DB_PASSWORD|${DB_PASS}|g" .env

    echo "✅ .env 已创建，密钥已自动生成"
    echo ""
    echo "⚠️  请编辑 .env 修改管理员密码等配置："
    echo "    vi $SCRIPT_DIR/.env"
    echo ""
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "请编辑 .env 后重新运行此脚本"
        exit 0
    fi
fi

echo ""
echo "🔨 步骤 1/3: 构建前端..."
docker compose -f docker-compose.prod.yml --profile build run --rm website-copy
docker compose -f docker-compose.prod.yml --profile build run --rm admin-build
docker compose -f docker-compose.prod.yml --profile build run --rm frontend-build

echo ""
echo "🐳 步骤 2/3: 构建后端镜像..."
docker compose -f docker-compose.prod.yml build server backend

echo ""
echo "🚀 步骤 3/3: 启动所有服务..."
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "⏳ 等待服务健康检查..."
sleep 10

docker compose -f docker-compose.prod.yml ps

PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-http://localhost}"

echo ""
echo "═══════════════════════════════════════"
echo "  ✅ 部署完成！"
echo ""
echo "  🌐 官网:     ${PUBLIC_ORIGIN}"
echo "  📱 用户端:   ${PUBLIC_ORIGIN}/app/"
echo "  🔧 管理后台: ${PUBLIC_ORIGIN}/admin/"
echo "  📡 API 文档: ${PUBLIC_ORIGIN}/docs"
echo "═══════════════════════════════════════"
echo ""
echo "常用命令:"
echo "  查看日志:   docker compose -f docker-compose.prod.yml logs -f"
echo "  重启服务:   docker compose -f docker-compose.prod.yml restart"
echo "  停止服务:   docker compose -f docker-compose.prod.yml down"
echo "  查看状态:   docker compose -f docker-compose.prod.yml ps"

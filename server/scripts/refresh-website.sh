#!/bin/bash
# 刷新网站静态文件到 Docker 卷（不重建整个项目）
# 用法: ./scripts/refresh-website.sh  或  bash scripts/refresh-website.sh

set -e
cd "$(dirname "$0")/.."
echo "正在刷新 website 到 volume website_dist..."

# 运行 website-copy 服务（仅此服务，profile build）
docker compose --profile build run --rm website-copy

echo "完成。请刷新浏览器（Ctrl+F5 强制刷新）查看最新导航栏。"

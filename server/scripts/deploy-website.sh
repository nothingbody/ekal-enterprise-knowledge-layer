#!/bin/bash
# 部署最新官网静态文件到生产环境
# 注意：admin-build 只更新 /admin/ 管理后台，官网根路径 / 来自 website_dist，需本脚本刷新
# 在服务器上执行前请先 git pull 或同步最新 website 目录

set -e
cd "$(dirname "$0")/.."

echo "1. 检查 website 源是否包含「技能市场」..."
if ! grep -q "技能市场" website/index.html 2>/dev/null; then
  echo "错误: website/index.html 中未找到「技能市场」链接。请先 git pull 或同步最新代码。"
  exit 1
fi
echo "   ✓ 源文件正常"

echo ""
echo "2. 刷新 website 到 Docker 卷..."
docker compose --profile build run --rm website-copy

echo ""
echo "3. 验证卷内 index.html..."
if docker run --rm -v server_website_dist:/data alpine grep -q "技能市场" /data/index.html 2>/dev/null; then
  echo "   ✓ 卷内已包含「技能市场」"
else
  echo "   警告: 卷内可能仍为旧版，请检查。"
fi

echo ""
echo "完成。请刷新浏览器 (Ctrl+F5) 查看导航栏。"

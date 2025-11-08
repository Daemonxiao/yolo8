#!/bin/bash
# AI视频识别系统 - 部署验证脚本

set -e

echo "=========================================="
echo "AI视频识别系统 - 部署验证"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1"
        return 1
    fi
}

# 1. 检查Docker
echo "1. 检查Docker环境..."
if command -v docker &> /dev/null; then
    docker --version | head -1
    check_status "Docker已安装"
else
    echo -e "${RED}✗ Docker未安装${NC}"
    echo "请先安装Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# 2. 检查Docker Compose
echo ""
echo "2. 检查Docker Compose..."
if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    docker-compose version 2>/dev/null || docker compose version
    check_status "Docker Compose已安装"
else
    echo -e "${RED}✗ Docker Compose未安装${NC}"
    echo "请先安装Docker Compose: brew install docker-compose"
    exit 1
fi

# 3. 检查配置文件
echo ""
echo "3. 检查配置文件..."
if [ -f "docker/.env" ]; then
    check_status "环境变量文件存在 (docker/.env)"
    
    # 检查关键配置
    if grep -q "SERVER_PUBLIC_URL=" docker/.env && \
       grep -q "DEVICE_PLATFORM_URL=" docker/.env && \
       grep -q "KAFKA_BOOTSTRAP_SERVERS=" docker/.env; then
        check_status "关键配置项已设置"
    else
        echo -e "${YELLOW}⚠${NC} 请检查配置是否完整"
    fi
else
    echo -e "${YELLOW}⚠${NC} 环境变量文件不存在"
    echo "  请创建 docker/.env 文件，参考 DEPLOY_GUIDE.md"
fi

if [ -f "config/default_config.yaml" ]; then
    check_status "主配置文件存在"
else
    echo -e "${RED}✗ 主配置文件不存在${NC}"
fi

# 4. 检查模型文件
echo ""
echo "4. 检查AI模型文件..."
model_count=$(find pt_dir -name "*.pt" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "$model_count" -gt 0 ]; then
    check_status "找到 $model_count 个模型文件"
    find pt_dir -name "*.pt" -type f | while read file; do
        size=$(ls -lh "$file" | awk '{print $5}')
        echo "  - $(basename $file): $size"
    done
else
    echo -e "${YELLOW}⚠${NC} 未找到模型文件"
    echo "  请将模型文件(.pt)放到 pt_dir/ 目录"
fi

# 5. 检查服务状态
echo ""
echo "5. 检查服务状态..."
cd docker 2>/dev/null || cd .

if docker-compose ps 2>/dev/null | grep -q "ai-detection"; then
    echo ""
    docker-compose ps
    echo ""
    
    # 检查容器运行状态
    if docker-compose ps | grep -q "ai-detection.*Up"; then
        check_status "AI识别服务正在运行"
        
        # 6. 测试健康检查
        echo ""
        echo "6. 测试API健康检查..."
        sleep 2
        response=$(curl -s http://localhost:8080/health 2>/dev/null || echo "")
        
        if echo "$response" | grep -q "healthy"; then
            check_status "API服务正常响应"
            echo ""
            echo "响应内容:"
            echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
        else
            echo -e "${YELLOW}⚠${NC} API服务未正常响应"
            echo "  请检查日志: docker-compose logs ai-detection"
        fi
    else
        echo -e "${YELLOW}⚠${NC} 服务未在运行状态"
    fi
    
    # 7. 检查Nginx
    echo ""
    echo "7. 检查Nginx服务..."
    if docker-compose ps | grep -q "nginx.*Up"; then
        check_status "Nginx服务正在运行"
    else
        echo -e "${YELLOW}⚠${NC} Nginx服务未运行"
    fi
    
else
    echo -e "${YELLOW}⚠${NC} 服务未启动"
    echo "  启动服务: cd docker && docker-compose up -d"
fi

cd ..

echo ""
echo "=========================================="
echo "验证完成！"
echo "=========================================="
echo ""
echo "下一步操作："
echo "1. 如果服务未启动: cd docker && docker-compose up -d"
echo "2. 查看日志: cd docker && docker-compose logs -f ai-detection"
echo "3. 测试场景下发: 参考 DEPLOY_GUIDE.md"
echo ""
echo "详细文档："
echo "- 部署指南: DEPLOY_GUIDE.md"
echo "- 产品设计: docs/PRODUCT_DESIGN.md"
echo "- 重构说明: REFACTOR_SUMMARY.md"
echo ""


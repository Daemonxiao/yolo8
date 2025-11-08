#!/bin/bash
# 实时视频检测系统安装脚本

set -e

echo "🚀 开始安装实时视频检测系统..."

# 检查Python版本
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ 错误: 需要Python 3.8或更高版本，当前版本: $python_version"
    exit 1
fi

echo "✅ Python版本检查通过: $python_version"

# 创建虚拟环境（可选）
if [ "$1" = "--venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✅ 虚拟环境已激活"
fi

# 安装依赖
echo "📦 安装Python依赖..."
pip install --upgrade pip
pip install -r requirements.txt

# 创建必要目录
echo "📁 创建必要目录..."
mkdir -p logs
mkdir -p results
mkdir -p results/images
mkdir -p models

# 设置权限
echo "🔐 设置文件权限..."
chmod +x scripts/*.sh

# 检查模型文件
echo "🔍 检查模型文件..."
if [ ! -f "models/yolov8n.pt" ]; then
    echo "📥 下载默认模型文件..."
    python3 -c "
from ultralytics import YOLO
model = YOLO('yolov8n.pt')
model.save('models/yolov8n.pt')
print('✅ 默认模型已下载')
"
fi

# 测试安装
echo "🧪 测试安装..."
python3 -c "
import sys
sys.path.append('src')
from src.config_manager import config_manager
print('✅ 配置管理器测试通过')
"

echo "🎉 安装完成！"
echo ""
echo "📋 下一步操作:"
echo "1. 配置检测模型: 将你的.pt文件放入models/目录"
echo "2. 修改配置文件: 编辑config/目录下的YAML文件"
echo "3. 启动系统: ./scripts/start.sh"
echo "4. 查看日志: tail -f logs/detection.log"
echo ""
echo "📖 详细文档请查看: docs/INSTALL.md"

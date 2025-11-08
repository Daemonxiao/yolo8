#!/bin/bash
# 实时视频检测系统启动脚本

set -e

# 配置参数
CONFIG_FILE=${1:-"config/default_config.yaml"}
LOG_FILE="logs/detection.log"
PID_FILE="logs/detection.pid"

echo "🚀 启动实时视频检测系统..."

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "⚠️  系统已在运行 (PID: $PID)"
        echo "如需重启，请先运行: ./scripts/stop.sh"
        exit 1
    else
        echo "🧹 清理旧的PID文件..."
        rm -f "$PID_FILE"
    fi
fi

# 检查配置文件
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ 配置文件不存在: $CONFIG_FILE"
    echo "可用配置文件:"
    ls -la config/*.yaml
    exit 1
fi

# 检查模型文件
MODEL_PATH=$(python3 -c "
import yaml
with open('$CONFIG_FILE', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
print(config['model']['path'])
" 2>/dev/null || echo "models/yolov8n.pt")

if [ ! -f "$MODEL_PATH" ]; then
    echo "❌ 模型文件不存在: $MODEL_PATH"
    echo "请将模型文件放入models/目录"
    exit 1
fi

# 创建日志目录
mkdir -p logs

# 设置环境变量（RTSP优化）
export OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp;fflags;nobuffer;flags;low_delay;reorder_queue_size;0;stimeout;5000000"

# 启动系统
echo "🌐 启动API服务器..."
echo "📄 配置文件: $CONFIG_FILE"
echo "📝 日志文件: $LOG_FILE"
echo "🔧 RTSP优化: TCP传输 + 低延迟"

# 后台启动
nohup python3 main.py --config "$CONFIG_FILE" > "$LOG_FILE" 2>&1 &
PID=$!

# 保存PID
echo "$PID" > "$PID_FILE"

# 等待启动
echo "⏳ 等待系统启动..."
sleep 3

# 检查启动状态
if ps -p "$PID" > /dev/null 2>&1; then
    echo "✅ 系统启动成功 (PID: $PID)"
    echo ""
    echo "📊 系统信息:"
    echo "  - API地址: http://localhost:8080"
    echo "  - 健康检查: http://localhost:8080/health"
    echo "  - 日志文件: $LOG_FILE"
    echo "  - 配置文件: $CONFIG_FILE"
    echo ""
    echo "📋 常用命令:"
    echo "  - 查看日志: tail -f $LOG_FILE"
    echo "  - 停止系统: ./scripts/stop.sh"
    echo "  - 重启系统: ./scripts/restart.sh"
    echo "  - 查看状态: curl http://localhost:8080/health"
else
    echo "❌ 系统启动失败"
    echo "📝 查看日志: tail -f $LOG_FILE"
    exit 1
fi

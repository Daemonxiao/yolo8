#!/bin/bash
# 实时视频检测系统停止脚本

PID_FILE="logs/detection.pid"

echo "🛑 停止实时视频检测系统..."

# 检查PID文件
if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  PID文件不存在，系统可能未运行"
    exit 0
fi

# 读取PID
PID=$(cat "$PID_FILE")

# 检查进程是否存在
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "⚠️  进程不存在 (PID: $PID)，清理PID文件"
    rm -f "$PID_FILE"
    exit 0
fi

echo "🔍 找到运行中的进程 (PID: $PID)"

# 优雅停止
echo "📤 发送停止信号..."
kill -TERM "$PID"

# 等待进程结束
echo "⏳ 等待进程结束..."
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ 系统已停止"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# 强制停止
echo "⚡ 强制停止进程..."
kill -KILL "$PID" 2>/dev/null || true

# 清理
rm -f "$PID_FILE"
echo "✅ 系统已停止"

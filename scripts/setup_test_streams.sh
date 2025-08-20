#!/bin/bash

# Make the script executable
chmod +x "$0"

# FFmpeg RTSP流模拟测试脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查FFmpeg安装
check_ffmpeg() {
    log_info "检查FFmpeg安装..."
    
    if ! command -v ffmpeg &> /dev/null; then
        log_error "FFmpeg未安装"
        echo "请先安装FFmpeg:"
        echo "  macOS: brew install ffmpeg"
        echo "  Ubuntu: sudo apt install ffmpeg"
        echo "  CentOS: sudo yum install ffmpeg"
        exit 1
    fi
    
    FFMPEG_VERSION=$(ffmpeg -version | head -n1)
    log_info "FFmpeg版本: $FFMPEG_VERSION"
}

# 创建测试视频
create_test_video() {
    log_info "创建测试视频文件..."
    
    TEST_VIDEO="test_video.mp4"
    
    if [ ! -f "$TEST_VIDEO" ]; then
        log_info "生成测试视频: $TEST_VIDEO"
        ffmpeg -f lavfi -i testsrc2=duration=60:size=1280x720:rate=30 \
               -f lavfi -i sine=frequency=1000:duration=60 \
               -c:v libx264 -preset fast -c:a aac \
               -t 60 "$TEST_VIDEO" -y
        log_info "测试视频创建完成"
    else
        log_info "测试视频已存在: $TEST_VIDEO"
    fi
}

# 启动简单的HTTP视频流（替代RTSP）
start_http_stream() {
    local port=${1:-8080}
    local video_file=${2:-test_video.mp4}
    
    log_info "启动HTTP视频流服务器..."
    log_info "端口: $port, 视频文件: $video_file"
    
    # 检查端口是否被占用
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_warn "端口 $port 已被占用"
        return 1
    fi
    
    # 启动HTTP流
    ffmpeg -re -stream_loop -1 -i "$video_file" \
           -c:v libx264 -preset ultrafast -tune zerolatency \
           -f mpegts "http://localhost:$port/stream.ts" &
    
    FFMPEG_PID=$!
    echo $FFMPEG_PID > ".http_server_$port.pid"
    
    log_info "HTTP流已启动 (PID: $FFMPEG_PID)"
    log_info "流地址: http://localhost:$port/stream.ts"
    
    return 0
}

# 使用Python创建简单的RTSP服务器
start_python_rtsp_server() {
    local port=${1:-8554}
    local video_file=${2:-test_video.mp4}
    
    log_info "启动Python RTSP服务器..."
    log_info "端口: $port, 视频文件: $video_file"
    
    # 检查端口是否被占用
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_warn "端口 $port 已被占用"
        return 1
    fi
    
    # 创建简单的RTSP服务器脚本
    cat > simple_rtsp_server.py << 'EOF'
#!/usr/bin/env python3
import subprocess
import threading
import time
import socket
import sys

class SimpleRTSPServer:
    def __init__(self, port=8554, video_file="test_video.mp4"):
        self.port = port
        self.video_file = video_file
        self.running = False
        
    def start(self):
        self.running = True
        
        # 使用ffmpeg转换视频为UDP流
        cmd = [
            'ffmpeg', '-re', '-stream_loop', '-1', '-i', self.video_file,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
            '-f', 'rtp', f'rtp://127.0.0.1:{self.port + 1000}'
        ]
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"RTSP server started on port {self.port}")
            print(f"Stream URL: rtsp://localhost:{self.port}/live")
            
            while self.running:
                time.sleep(1)
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            process.terminate()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8554
    video_file = sys.argv[2] if len(sys.argv) > 2 else "test_video.mp4"
    
    server = SimpleRTSPServer(port, video_file)
    server.start()
EOF
    
    # 启动Python RTSP服务器
    python3 simple_rtsp_server.py "$port" "$video_file" &
    
    PYTHON_PID=$!
    echo $PYTHON_PID > ".rtsp_server_$port.pid"
    
    log_info "Python RTSP服务器已启动 (PID: $PYTHON_PID)"
    log_info "流地址: rtsp://localhost:$port/live"
    
    return 0
}

# 使用文件方式模拟视频流
start_file_stream() {
    local video_file=${1:-test_video.mp4}
    
    log_info "使用文件模拟视频流: $video_file"
    
    if [ ! -f "$video_file" ]; then
        log_error "视频文件不存在: $video_file"
        return 1
    fi
    
    # 复制文件到固定位置用于测试
    cp "$video_file" "current_stream.mp4"
    
    log_info "文件流已准备就绪: current_stream.mp4"
    log_info "可以直接使用文件路径进行测试"
    
    return 0
}

# 启动多个RTSP流
start_multiple_streams() {
    log_info "启动多个测试RTSP流..."
    
    # 流1: 主测试流
    start_rtsp_server 8554 "main" "test_video.mp4"
    sleep 2
    
    # 流2: 备用测试流
    start_rtsp_server 8555 "backup" "test_video.mp4"
    sleep 2
    
    # 流3: 高质量流
    start_rtsp_server 8556 "hq" "test_video.mp4"
    sleep 2
    
    log_info "所有测试流已启动"
    echo
    echo "可用的RTSP流地址:"
    echo "  rtsp://localhost:8554/main"
    echo "  rtsp://localhost:8555/backup"
    echo "  rtsp://localhost:8556/hq"
}

# 停止RTSP服务器
stop_rtsp_servers() {
    log_info "停止所有RTSP流服务器..."
    
    for port in 8554 8555 8556; do
        PID_FILE=".rtsp_server_$port.pid"
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                log_info "停止端口 $port 的服务器 (PID: $PID)"
                kill "$PID"
                sleep 1
                
                # 强制终止
                if kill -0 "$PID" 2>/dev/null; then
                    kill -9 "$PID"
                fi
            fi
            rm -f "$PID_FILE"
        fi
    done
    
    # 清理可能的残留进程
    pkill -f "ffmpeg.*rtsp://localhost" || true
    
    log_info "所有RTSP服务器已停止"
}

# 测试RTSP流连接
test_rtsp_connection() {
    local rtsp_url=${1:-"rtsp://localhost:8554/main"}
    
    log_info "测试RTSP流连接: $rtsp_url"
    
    # 使用ffprobe测试连接
    if ffprobe -v quiet -select_streams v:0 -show_entries stream=width,height,r_frame_rate -of csv=p=0 "$rtsp_url" 2>/dev/null; then
        log_info "✅ RTSP流连接成功"
        
        # 获取流信息
        STREAM_INFO=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=width,height,r_frame_rate -of csv=p=0 "$rtsp_url" 2>/dev/null)
        log_info "流信息: $STREAM_INFO"
        
        return 0
    else
        log_error "❌ RTSP流连接失败"
        return 1
    fi
}

# 创建测试配置
create_test_config() {
    log_info "创建测试配置文件..."
    
    cat > test_streams_config.json << EOF
{
  "test_streams": [
    {
      "stream_id": "test_camera_001",
      "name": "测试摄像头1",
      "rtsp_url": "rtsp://localhost:8554/main",
      "confidence_threshold": 0.25,
      "fps_limit": 10
    },
    {
      "stream_id": "test_camera_002", 
      "name": "测试摄像头2",
      "rtsp_url": "rtsp://localhost:8555/backup",
      "confidence_threshold": 0.3,
      "fps_limit": 15
    },
    {
      "stream_id": "test_camera_003",
      "name": "测试摄像头3",
      "rtsp_url": "rtsp://localhost:8556/hq",
      "confidence_threshold": 0.35,
      "fps_limit": 20
    }
  ]
}
EOF
    
    log_info "测试配置已保存到: test_streams_config.json"
}

# 使用系统API注册测试流
register_test_streams() {
    local api_url=${1:-"http://localhost:8080"}
    
    log_info "注册测试流到检测系统..."
    
    if [ ! -f "test_streams_config.json" ]; then
        log_error "测试配置文件不存在"
        return 1
    fi
    
    # 检查API服务器状态
    if ! curl -s "$api_url/health" >/dev/null; then
        log_error "无法连接到API服务器: $api_url"
        log_info "请先启动检测系统: python main.py"
        return 1
    fi
    
    # 注册每个测试流
    jq -c '.test_streams[]' test_streams_config.json | while read stream; do
        STREAM_ID=$(echo "$stream" | jq -r '.stream_id')
        
        log_info "注册流: $STREAM_ID"
        
        RESPONSE=$(curl -s -X POST "$api_url/api/v1/streams" \
                       -H "Content-Type: application/json" \
                       -d "$stream")
        
        SUCCESS=$(echo "$RESPONSE" | jq -r '.success // false')
        
        if [ "$SUCCESS" = "true" ]; then
            log_info "✅ 流注册成功: $STREAM_ID"
        else
            ERROR_MSG=$(echo "$RESPONSE" | jq -r '.error // "未知错误"')
            log_error "❌ 流注册失败: $STREAM_ID - $ERROR_MSG"
        fi
    done
}

# 显示状态信息
show_status() {
    echo
    echo "===================== 状态信息 ====================="
    
    # 检查RTSP服务器状态
    echo "RTSP服务器状态:"
    for port in 8554 8555 8556; do
        PID_FILE=".rtsp_server_$port.pid"
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "  ✅ 端口 $port: 运行中 (PID: $PID)"
            else
                echo "  ❌ 端口 $port: 已停止"
            fi
        else
            echo "  ❌ 端口 $port: 未启动"
        fi
    done
    
    echo
    echo "可用的RTSP流地址:"
    echo "  rtsp://localhost:8554/main"
    echo "  rtsp://localhost:8555/backup" 
    echo "  rtsp://localhost:8556/hq"
    
    echo
    echo "测试命令:"
    echo "  ffplay rtsp://localhost:8554/main"
    echo "  ffprobe rtsp://localhost:8554/main"
}

# 显示帮助信息
show_help() {
    cat << EOF
FFmpeg RTSP流模拟测试脚本

用法: $0 [命令] [选项]

命令:
  setup     创建测试视频和配置文件
  start     启动RTSP流服务器
  stop      停止所有RTSP流服务器  
  test      测试RTSP流连接
  register  注册测试流到检测系统
  status    显示服务器状态
  clean     清理测试文件

选项:
  -p, --port PORT       指定RTSP端口 (默认: 8554)
  -s, --stream NAME     指定流名称 (默认: main)
  -v, --video FILE      指定视频文件 (默认: test_video.mp4)
  -a, --api URL         指定API地址 (默认: http://localhost:8080)
  -h, --help            显示帮助信息

示例:
  $0 setup              # 创建测试环境
  $0 start              # 启动默认RTSP流
  $0 start -p 8555 -s backup    # 启动自定义流
  $0 test               # 测试默认流连接
  $0 register           # 注册流到检测系统
  $0 stop               # 停止所有流
  $0 clean              # 清理测试文件

EOF
}

# 清理测试文件
clean_test_files() {
    log_info "清理测试文件..."
    
    # 停止服务器
    stop_rtsp_servers
    
    # 删除测试文件
    rm -f test_video.mp4
    rm -f test_streams_config.json
    rm -f .rtsp_server_*.pid
    
    log_info "清理完成"
}

# 主函数
main() {
    COMMAND="setup"
    PORT=8554
    STREAM_NAME="main"
    VIDEO_FILE="test_video.mp4"
    API_URL="http://localhost:8080"
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            setup|start|stop|test|register|status|clean)
                COMMAND="$1"
                shift
                ;;
            -p|--port)
                PORT="$2"
                shift 2
                ;;
            -s|--stream)
                STREAM_NAME="$2"
                shift 2
                ;;
            -v|--video)
                VIDEO_FILE="$2"
                shift 2
                ;;
            -a|--api)
                API_URL="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 执行命令
    case "$COMMAND" in
        setup)
            check_ffmpeg
            create_test_video
            create_test_config
            log_info "测试环境设置完成"
            ;;
        start)
            check_ffmpeg
            if [ ! -f "$VIDEO_FILE" ]; then
                create_test_video
            fi
            
            if [[ "$PORT" =~ ^(8554|8555|8556)$ ]]; then
                start_multiple_streams
            else
                start_rtsp_server "$PORT" "$STREAM_NAME" "$VIDEO_FILE"
            fi
            ;;
        stop)
            stop_rtsp_servers
            ;;
        test)
            test_rtsp_connection "rtsp://localhost:$PORT/$STREAM_NAME"
            ;;
        register)
            register_test_streams "$API_URL"
            ;;
        status)
            show_status
            ;;
        clean)
            clean_test_files
            ;;
        *)
            log_error "未知命令: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

# 脚本入口
main "$@"

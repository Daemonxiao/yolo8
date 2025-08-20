#!/bin/bash

# 实时视频检测系统启动脚本

set -e

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

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

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# 检查Python版本
check_python() {
    log_info "检查Python版本..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python3未安装"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    log_info "Python版本: $PYTHON_VERSION"
    
    # 检查版本是否大于等于3.8
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
        log_info "Python版本检查通过"
    else
        log_error "需要Python 3.8或更高版本"
        exit 1
    fi
}

# 检查依赖包
check_dependencies() {
    log_info "检查依赖包..."
    
    # 检查关键依赖
    REQUIRED_PACKAGES=("torch" "ultralytics" "opencv-python" "flask" "pyyaml" "requests")
    MISSING_PACKAGES=()
    
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if ! python3 -c "import ${package//-/_}" &> /dev/null; then
            MISSING_PACKAGES+=("$package")
        fi
    done
    
    if [ ${#MISSING_PACKAGES[@]} -ne 0 ]; then
        log_warn "缺少依赖包: ${MISSING_PACKAGES[*]}"
        log_info "正在安装依赖包..."
        pip3 install -r requirements.txt
    else
        log_info "依赖包检查通过"
    fi
}

# 检查模型文件
check_model() {
    log_info "检查模型文件..."
    
    MODEL_PATH="constuction_waste/best.pt"
    if [ ! -f "$MODEL_PATH" ]; then
        log_error "模型文件不存在: $MODEL_PATH"
        log_info "请确保模型文件存在或修改配置文件中的模型路径"
        exit 1
    else
        log_info "模型文件检查通过: $MODEL_PATH"
    fi
}

# 检查配置文件
check_config() {
    log_info "检查配置文件..."
    
    CONFIG_FILE="${CONFIG_FILE:-config/default_config.yaml}"
    if [ ! -f "$CONFIG_FILE" ]; then
        log_error "配置文件不存在: $CONFIG_FILE"
        exit 1
    else
        log_info "配置文件: $CONFIG_FILE"
    fi
}

# 创建必要目录
create_directories() {
    log_info "创建必要目录..."
    
    DIRS=("logs" "results" "results/images")
    for dir in "${DIRS[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log_debug "创建目录: $dir"
        fi
    done
}

# 检查端口占用
check_port() {
    local port=${1:-8080}
    
    if command -v lsof &> /dev/null; then
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
            log_warn "端口 $port 已被占用"
            return 1
        fi
    elif command -v netstat &> /dev/null; then
        if netstat -tuln | grep ":$port " >/dev/null; then
            log_warn "端口 $port 已被占用"
            return 1
        fi
    fi
    
    return 0
}

# 启动系统
start_system() {
    log_info "启动实时视频检测系统..."
    
    # 解析命令行参数
    PYTHON_ARGS=()
    
    # 配置文件
    if [ -n "$CONFIG_FILE" ]; then
        PYTHON_ARGS+=("--config" "$CONFIG_FILE")
    fi
    
    # 守护进程模式
    if [ "$DAEMON_MODE" = "true" ]; then
        PYTHON_ARGS+=("--daemon")
    fi
    
    # 检查端口
    API_PORT=$(python3 -c "
import sys, os
sys.path.append('src')
from src.config_manager import config_manager
print(config_manager.get('api.port', 8080))
" 2>/dev/null || echo "8080")
    
    if ! check_port "$API_PORT"; then
        log_error "端口 $API_PORT 已被占用，请检查或修改配置"
        exit 1
    fi
    
    # 启动系统
    log_info "正在启动系统... (端口: $API_PORT)"
    
    if [ "$DAEMON_MODE" = "true" ]; then
        nohup python3 main.py "${PYTHON_ARGS[@]}" > logs/system.log 2>&1 &
        PID=$!
        echo $PID > .system.pid
        log_info "系统已在后台启动 (PID: $PID)"
        log_info "日志文件: logs/system.log"
    else
        python3 main.py "${PYTHON_ARGS[@]}"
    fi
}

# 停止系统
stop_system() {
    log_info "停止系统..."
    
    if [ -f ".system.pid" ]; then
        PID=$(cat .system.pid)
        if kill -0 "$PID" 2>/dev/null; then
            log_info "正在停止进程 $PID..."
            kill -TERM "$PID"
            sleep 2
            
            if kill -0 "$PID" 2>/dev/null; then
                log_warn "进程未正常停止，强制终止..."
                kill -KILL "$PID"
            fi
        fi
        rm -f .system.pid
        log_info "系统已停止"
    else
        log_warn "未找到PID文件"
    fi
}

# 检查系统状态
check_status() {
    log_info "检查系统状态..."
    
    if [ -f ".system.pid" ]; then
        PID=$(cat .system.pid)
        if kill -0 "$PID" 2>/dev/null; then
            log_info "系统正在运行 (PID: $PID)"
            
            # 尝试检查API服务
            API_PORT=$(python3 -c "
import sys, os
sys.path.append('src')
from src.config_manager import config_manager
print(config_manager.get('api.port', 8080))
" 2>/dev/null || echo "8080")
            
            if command -v curl &> /dev/null; then
                if curl -s "http://localhost:$API_PORT/health" >/dev/null; then
                    log_info "API服务正常 (http://localhost:$API_PORT)"
                else
                    log_warn "API服务不可访问"
                fi
            fi
        else
            log_warn "PID文件存在但进程未运行"
            rm -f .system.pid
        fi
    else
        log_info "系统未运行"
    fi
}

# 显示帮助信息
show_help() {
    cat << EOF
实时视频检测系统启动脚本

用法: $0 [选项] [命令]

命令:
  start     启动系统 (默认)
  stop      停止系统
  restart   重启系统
  status    查看状态

选项:
  -c, --config FILE     指定配置文件 (默认: config/default_config.yaml)
  -d, --daemon          以守护进程模式运行
  -h, --help            显示帮助信息

环境变量:
  CONFIG_FILE           配置文件路径
  DAEMON_MODE           守护进程模式 (true/false)

示例:
  $0 start                              # 启动系统
  $0 start -c config/my_config.yaml    # 使用自定义配置启动
  $0 start -d                          # 后台运行
  $0 stop                              # 停止系统
  $0 status                            # 查看状态

EOF
}

# 主函数
main() {
    # 解析命令行参数
    COMMAND="start"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            start|stop|restart|status)
                COMMAND="$1"
                shift
                ;;
            -c|--config)
                CONFIG_FILE="$2"
                shift 2
                ;;
            -d|--daemon)
                DAEMON_MODE="true"
                shift
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
        start)
            # 系统检查
            check_python
            check_dependencies
            check_model
            check_config
            create_directories
            
            # 启动系统
            start_system
            ;;
        stop)
            stop_system
            ;;
        restart)
            stop_system
            sleep 2
            
            # 重新检查
            check_python
            check_config
            create_directories
            
            start_system
            ;;
        status)
            check_status
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

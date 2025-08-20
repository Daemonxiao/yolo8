# FFmpeg RTSP流测试指南

本指南介绍如何使用FFmpeg模拟RTSP流来测试实时视频检测系统。

## 📋 准备工作

### 1. 安装FFmpeg

**macOS (使用Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**CentOS/RHEL:**
```bash
sudo yum install epel-release
sudo yum install ffmpeg
```

**验证安装:**
```bash
ffmpeg -version
```

### 2. 检查依赖工具

**jq (JSON处理工具):**
```bash
# macOS
brew install jq

# Ubuntu
sudo apt install jq

# CentOS
sudo yum install jq
```

## 🚀 快速开始

### 方法一：使用自动化脚本

1. **设置测试环境:**
```bash
./scripts/setup_test_streams.sh setup
```

2. **启动RTSP流:**
```bash
./scripts/setup_test_streams.sh start
```

3. **启动检测系统:**
```bash
python main.py
```

4. **注册测试流:**
```bash
./scripts/setup_test_streams.sh register
```

5. **查看状态:**
```bash
./scripts/setup_test_streams.sh status
```

### 方法二：手动操作

#### 1. 创建测试视频

**生成彩色测试图案视频:**
```bash
ffmpeg -f lavfi -i testsrc2=duration=60:size=1280x720:rate=30 \
       -f lavfi -i sine=frequency=1000:duration=60 \
       -c:v libx264 -preset fast -c:a aac \
       -t 60 test_video.mp4
```

**使用现有视频文件:**
```bash
# 如果你有现有的MP4文件，可以直接使用
cp your_video.mp4 test_video.mp4
```

#### 2. 启动RTSP流服务器

**单个RTSP流:**
```bash
ffmpeg -re -stream_loop -1 -i test_video.mp4 \
       -c:v libx264 -preset ultrafast -tune zerolatency \
       -c:a aac -f rtsp rtsp://localhost:8554/live
```

**多个RTSP流 (在不同终端中运行):**
```bash
# 流1 - 端口8554
ffmpeg -re -stream_loop -1 -i test_video.mp4 \
       -c:v libx264 -preset ultrafast -tune zerolatency \
       -c:a aac -f rtsp rtsp://localhost:8554/main &

# 流2 - 端口8555  
ffmpeg -re -stream_loop -1 -i test_video.mp4 \
       -c:v libx264 -preset ultrafast -tune zerolatency \
       -c:a aac -f rtsp rtsp://localhost:8555/backup &

# 流3 - 端口8556
ffmpeg -re -stream_loop -1 -i test_video.mp4 \
       -c:v libx264 -preset ultrafast -tune zerolatency \
       -c:a aac -f rtsp rtsp://localhost:8556/hq &
```

#### 3. 测试RTSP流连接

**使用FFprobe检查流信息:**
```bash
ffprobe -v quiet -select_streams v:0 \
        -show_entries stream=width,height,r_frame_rate \
        -of csv=p=0 rtsp://localhost:8554/main
```

**使用FFplay播放测试:**
```bash
ffplay rtsp://localhost:8554/main
```

**使用curl测试(可选):**
```bash
curl -v rtsp://localhost:8554/main
```

## 🔧 高级配置

### 1. 不同质量的RTSP流

**高质量流 (1080p, 高码率):**
```bash
ffmpeg -re -stream_loop -1 -i test_video.mp4 \
       -s 1920x1080 -b:v 2M -maxrate 2M -bufsize 4M \
       -c:v libx264 -preset medium -tune zerolatency \
       -c:a aac -f rtsp rtsp://localhost:8554/hq
```

**中等质量流 (720p, 中码率):**
```bash
ffmpeg -re -stream_loop -1 -i test_video.mp4 \
       -s 1280x720 -b:v 1M -maxrate 1M -bufsize 2M \
       -c:v libx264 -preset fast -tune zerolatency \
       -c:a aac -f rtsp rtsp://localhost:8555/mq
```

**低质量流 (480p, 低码率):**
```bash
ffmpeg -re -stream_loop -1 -i test_video.mp4 \
       -s 854x480 -b:v 500k -maxrate 500k -bufsize 1M \
       -c:v libx264 -preset ultrafast -tune zerolatency \
       -c:a aac -f rtsp rtsp://localhost:8556/lq
```

### 2. 使用摄像头作为源

**macOS (使用内置摄像头):**
```bash
ffmpeg -f avfoundation -i "0" -c:v libx264 -preset ultrafast \
       -tune zerolatency -f rtsp rtsp://localhost:8554/camera
```

**Linux (使用USB摄像头):**
```bash
ffmpeg -f v4l2 -i /dev/video0 -c:v libx264 -preset ultrafast \
       -tune zerolatency -f rtsp rtsp://localhost:8554/camera
```

**Windows (使用DirectShow):**
```bash
ffmpeg -f dshow -i video="USB Camera" -c:v libx264 -preset ultrafast \
       -tune zerolatency -f rtsp rtsp://localhost:8554/camera
```

### 3. 添加动态内容

**添加时间戳叠加:**
```bash
ffmpeg -re -stream_loop -1 -i test_video.mp4 \
       -vf "drawtext=text='%{localtime}':fontsize=30:fontcolor=white:x=10:y=10" \
       -c:v libx264 -preset ultrafast -tune zerolatency \
       -c:a aac -f rtsp rtsp://localhost:8554/timestamped
```

**添加移动的文字:**
```bash
ffmpeg -re -stream_loop -1 -i test_video.mp4 \
       -vf "drawtext=text='MOVING TEXT':fontsize=40:fontcolor=red:x=w-tw*t/10:y=h/2" \
       -c:v libx264 -preset ultrafast -tune zerolatency \
       -c:a aac -f rtsp rtsp://localhost:8554/moving
```

## 📡 系统集成测试

### 1. 注册RTSP流到检测系统

```bash
# 注册主测试流
curl -X POST http://localhost:8080/api/v1/streams \
  -H "Content-Type: application/json" \
  -d '{
    "stream_id": "test_rtsp_001",
    "rtsp_url": "rtsp://localhost:8554/main",
    "name": "FFmpeg测试流1",
    "confidence_threshold": 0.25,
    "fps_limit": 10,
    "callback_url": "http://localhost:5000/callback"
  }'

# 注册备用测试流
curl -X POST http://localhost:8080/api/v1/streams \
  -H "Content-Type: application/json" \
  -d '{
    "stream_id": "test_rtsp_002", 
    "rtsp_url": "rtsp://localhost:8555/backup",
    "name": "FFmpeg测试流2",
    "confidence_threshold": 0.3,
    "fps_limit": 15
  }'
```

### 2. 启动检测

```bash
# 启动第一个流的检测
curl -X POST http://localhost:8080/api/v1/streams/test_rtsp_001/start

# 启动第二个流的检测
curl -X POST http://localhost:8080/api/v1/streams/test_rtsp_002/start
```

### 3. 监控检测状态

```bash
# 获取流状态
curl http://localhost:8080/api/v1/streams/test_rtsp_001

# 获取系统统计
curl http://localhost:8080/api/v1/stats

# 获取所有流
curl http://localhost:8080/api/v1/streams
```

## 🛠️ 故障排除

### 常见问题

**1. RTSP流启动失败**
```bash
# 检查端口是否被占用
lsof -i :8554

# 终止占用端口的进程
sudo kill -9 <PID>
```

**2. 流连接超时**
```bash
# 检查防火墙设置
sudo ufw status

# 临时开放端口 (Ubuntu)
sudo ufw allow 8554/tcp
```

**3. 视频编码错误**
```bash
# 检查FFmpeg编码器支持
ffmpeg -encoders | grep h264

# 使用软件编码器
ffmpeg ... -c:v libx264 ...
```

**4. 内存不足**
```bash
# 降低视频质量
ffmpeg ... -s 640x480 -b:v 500k ...

# 增加缓冲区大小
ffmpeg ... -bufsize 1M ...
```

### 调试命令

**查看详细日志:**
```bash
ffmpeg -loglevel debug -re -stream_loop -1 -i test_video.mp4 \
       -c:v libx264 -f rtsp rtsp://localhost:8554/debug
```

**测试网络连接:**
```bash
# 测试TCP连接
telnet localhost 8554

# 测试RTSP协议
ffprobe -v debug rtsp://localhost:8554/main
```

**监控系统资源:**
```bash
# 监控CPU和内存使用
top -p $(pgrep ffmpeg)

# 监控网络流量
iftop -i lo
```

## 📋 测试清单

### 基础功能测试
- [ ] FFmpeg成功安装
- [ ] 测试视频生成成功
- [ ] RTSP流启动成功
- [ ] 流连接测试通过
- [ ] 检测系统能够连接流
- [ ] 检测结果正常输出

### 性能测试
- [ ] 单流检测性能
- [ ] 多流并发检测
- [ ] 长时间运行稳定性
- [ ] 内存使用情况
- [ ] CPU使用情况

### 异常测试
- [ ] 网络中断恢复
- [ ] 流源断开重连
- [ ] 系统重启恢复
- [ ] 异常流格式处理

## 🧹 清理环境

**停止所有RTSP流:**
```bash
./scripts/setup_test_streams.sh stop
# 或手动终止
pkill -f "ffmpeg.*rtsp"
```

**清理测试文件:**
```bash
./scripts/setup_test_streams.sh clean
# 或手动清理
rm -f test_video.mp4 test_streams_config.json .rtsp_server_*.pid
```

通过以上步骤，你可以完整地测试实时视频检测系统的各项功能，确保系统在真实环境中的稳定性和可靠性。


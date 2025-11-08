# AI视频识别系统 Docker镜像
# 基于Python 3.10，包含OpenCV和YOLOv8依赖
FROM docker.m.daocloud.io/library/python:3.10-slim

# 设置工作目录
WORKDIR /app

# 配置apt使用阿里云镜像源
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV依赖（Debian 13+使用libgl1代替libgl1-mesa-glx）
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # GStreamer支持（用于RTSP）
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    # 工具
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装Python依赖（使用清华源）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn && \
    pip cache purge

# 复制应用代码
COPY main.py .
COPY src/ ./src/

# 创建必要目录
RUN mkdir -p logs results pt_dir config

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai \
    OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp;fflags;nobuffer;flags;low_delay;reorder_queue_size;0;stimeout;5000000"

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 启动命令
CMD ["python", "main.py", "--config", "config/default_config.yaml"]

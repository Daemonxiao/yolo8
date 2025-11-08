# 🚀 快速部署指南

本指南帮助你在5分钟内完成 AI视频识别系统的部署。

## 📋 部署前检查清单

在开始部署前，请确认以下信息：

- [ ] ✅ Docker 已安装并运行
- [ ] ✅ Docker Compose 已安装
- [ ] ✅ 服务器公网地址或域名（用于外部访问告警图片）
- [ ] ✅ 外部设备管理平台地址（提供 getPlayUrl 和 heartBeat 接口）
- [ ] ✅ 外部Kafka服务器地址
- [ ] ✅ AI模型文件已准备（放在 `pt_dir/` 目录）

## 🔧 步骤1：配置环境变量

创建环境变量文件：

```bash
cd /Users/mx/PythonProject/yolo8/docker
cat > .env << 'EOF'
# 服务器配置（必须）⭐
SERVER_PUBLIC_URL=http://你的服务器IP或域名

# 设备平台配置（必须）⭐
DEVICE_PLATFORM_URL=http://设备平台IP:端口
DEVICE_PLATFORM_TIMEOUT=10
DEVICE_PLATFORM_RETRY=3

# Kafka配置（必须）⭐
KAFKA_BOOTSTRAP_SERVERS=Kafka服务器IP:9092
KAFKA_TOPIC=event-alarm
KAFKA_ENABLED=true

# 日志配置
LOG_LEVEL=INFO
EOF
```

### 配置说明

#### SERVER_PUBLIC_URL
外部平台访问告警图片的URL地址，格式示例：
- 公网IP: `http://123.45.67.89`
- 域名: `http://ai.example.com`
- HTTPS: `https://ai.example.com`
- 本地测试: `http://localhost:8080`

#### DEVICE_PLATFORM_URL
设备管理平台地址，提供以下接口：
- `POST /device/getPlayUrl` - 获取视频流地址
- `POST /device/heartBeat` - 设备心跳保活

#### KAFKA_BOOTSTRAP_SERVERS
外部Kafka集群地址，系统会将告警推送到此Kafka。

## 📦 步骤2：准备模型文件

确保AI模型文件在正确位置：

```bash
ls -lh ../pt_dir/
# 应该看到：
# fire_smoke/best.pt      - 火灾检测模型
# person/best.pt          - 人员检测模型
# constuction_waste/      - 建筑垃圾检测模型
# luotu/best.pt           - 其他检测模型
```

## 🐳 步骤3：启动服务

### 方式1：使用 docker-compose（推荐）

```bash
cd /Users/mx/PythonProject/yolo8/docker

# 构建镜像
docker-compose build

# 启动服务（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f ai-detection

# 查看服务状态
docker-compose ps
```

### 方式2：使用脚本

```bash
cd /Users/mx/PythonProject/yolo8

# 启动
./scripts/start.sh

# 停止
./scripts/stop.sh
```

## ✅ 步骤4：验证部署

### 4.1 健康检查

```bash
curl http://localhost:8080/health
```

期望输出：
```json
{
  "status": "healthy",
  "timestamp": 1699420800.0,
  "version": "v1",
  "streams": 0
}
```

### 4.2 测试场景下发接口

创建测试请求文件：

```bash
cat > test_scene_deploy.json << 'EOF'
{
  "devices": [
    {
      "deviceGbCode": "31011500001320000001",
      "area": "(100,100),(500,100),(500,400),(100,400)"
    }
  ],
  "scene": "明火告警",
  "algorithm": "火焰检测",
  "startDate": "2024-11-08 10:00:00",
  "endDate": "2025-11-08 10:00:00"
}
EOF
```

发送请求：

```bash
curl -X POST http://localhost:8080/api/v1/scene/deploy \
  -H "Content-Type: application/json" \
  -d @test_scene_deploy.json
```

期望输出：
```json
{
  "status": 0,
  "message": "场景部署成功",
  "data": {
    "deployed_devices": 1,
    "failed_devices": 0
  }
}
```

### 4.3 查看场景列表

```bash
curl http://localhost:8080/api/v1/scenes
```

### 4.4 查看日志

```bash
# 查看实时日志
docker-compose logs -f ai-detection

# 查看最近100行
docker-compose logs --tail=100 ai-detection
```

## 🔍 步骤5：验证外部集成

### 5.1 检查设备平台调用

查看日志中是否有：
```
INFO - 调用设备平台接口: getPlayUrl, deviceGbCode=31011500001320000001
INFO - 获取流地址成功: rtsp://...
INFO - 设备 31011500001320000001 心跳成功
```

### 5.2 检查Kafka推送

在外部Kafka消费者端验证是否能收到 `event-alarm` topic 的消息：

```bash
# 在Kafka服务器上
kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic event-alarm --from-beginning
```

期望看到告警消息：
```json
{
  "scene": "火警",
  "alarmTime": "2024-11-08 10:04:29",
  "pic": "http://你的服务器/results/2024-11-08/camera_001/10-04-29-123_frame_1/annotated.jpg",
  "deviceGbCode": "31011500001320000001",
  "record": "http://你的服务器/results/videos/camera_001_20241108_100429.mp4"
}
```

### 5.3 验证图片URL访问

当有告警时，复制Kafka消息中的 `pic` URL，在浏览器中访问，应该能看到告警图片。

如果无法访问，检查：
1. `SERVER_PUBLIC_URL` 配置是否正确
2. Nginx是否正确配置并运行
3. 防火墙/安全组是否开放80端口

## 🎯 常用API接口

### 场景管理

```bash
# 场景下发
POST /api/v1/scene/deploy

# 停止场景
POST /api/v1/scene/{scene_id}/stop

# 获取场景信息
GET /api/v1/scene/{scene_id}

# 获取所有场景
GET /api/v1/scenes
```

### 流管理（内部使用）

```bash
# 获取所有流
GET /api/v1/streams

# 获取流详情
GET /api/v1/streams/{stream_id}

# 停止流
POST /api/v1/streams/{stream_id}/stop
```

## 🔧 常见问题

### 问题1：容器无法启动

```bash
# 查看详细日志
docker-compose logs ai-detection

# 检查配置文件
docker-compose config

# 重新构建
docker-compose build --no-cache
docker-compose up -d
```

### 问题2：无法连接设备平台

检查：
1. `DEVICE_PLATFORM_URL` 是否正确
2. 网络是否互通：`curl http://设备平台IP:端口/health`
3. 防火墙是否放行

### 问题3：Kafka推送失败

检查：
1. `KAFKA_BOOTSTRAP_SERVERS` 是否正确
2. Kafka服务是否运行：`telnet Kafka服务器IP 9092`
3. Topic是否已创建：`kafka-topics.sh --list --bootstrap-server localhost:9092`

### 问题4：告警图片无法访问

检查：
1. `SERVER_PUBLIC_URL` 是否配置为可公网访问的地址
2. Nginx是否运行：`docker-compose ps nginx`
3. 防火墙80端口是否开放
4. 检查Nginx日志：`docker-compose logs nginx`

### 问题5：检测结果不准确

调整配置文件 `config/default_config.yaml`：
```yaml
detection:
  confidence_threshold: 0.5  # 降低阈值增加检测数量
  iou_threshold: 0.45
  fps_limit: 1  # 增加处理帧率
```

## 📊 性能优化

### CPU优化

```yaml
# docker-compose.yml
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 8G
```

### GPU加速（需要NVIDIA GPU）

1. 安装 nvidia-docker2
2. 修改 docker-compose.yml：

```yaml
services:
  ai-detection:
    runtime: nvidia
    environment:
      - USE_GPU=true
      - NVIDIA_VISIBLE_DEVICES=all
```

## 🛑 停止服务

```bash
cd /Users/mx/PythonProject/yolo8/docker

# 停止服务
docker-compose down

# 停止并删除数据卷（慎用）
docker-compose down -v
```

## 📚 更多文档

- 详细产品设计：`docs/PRODUCT_DESIGN.md`
- 重构说明：`REFACTOR_SUMMARY.md`
- 接入文档：`docs/接入文档.md`

## 🆘 技术支持

如有问题，请查看：
1. 日志文件：`logs/detection.log`
2. Docker日志：`docker-compose logs`
3. 配置文件：`config/default_config.yaml`

---

**部署完成！** 🎉

系统现在已经运行，可以接收场景下发请求并进行实时视频分析了。


# AI视频识别系统 - 厂商接入版

基于YOLOv8的实时视频分析系统，符合AI识别厂商接入规范。

## 🎯 项目定位

我们是**AI识别算法厂商**（第三方服务提供商），为监控平台提供实时视频AI识别服务。

## 📋 接口角色

| 接口 | 方向 | 说明 | 我们的角色 |
|------|------|------|-----------|
| POST /api/v1/scene/deploy | 监控平台 → 我们 | 场景下发 | **服务提供方**（我们实现） |
| POST /device/getPlayUrl | 我们 → 设备平台 | 获取流地址 | **服务调用方**（我们调用） |
| POST /device/heartBeat | 我们 → 设备平台 | 心跳保活 | **服务调用方**（每10秒） |
| Kafka: event-alarm | 我们 → Kafka | 告警推送 | **消息生产者**（我们推送） |

## 🚀 快速开始

### 1. 环境要求

- Docker & Docker Compose
- Python 3.9+（如果不使用Docker）
- AI模型文件（`.pt`）

### 2. 配置外部依赖

在 `config/default_config.yaml` 中配置：

```yaml
# 服务器公网地址（重要！用于生成告警图片URL）
server:
  public_url: "http://your-server-ip:8080"  # 或域名

# 设备平台地址（重要！必须配置）
device_platform:
  base_url: "http://设备平台IP:端口"
  
# Kafka配置（重要！必须配置）
kafka:
  bootstrap_servers: "Kafka地址:9092"
  topic: "event-alarm"
```

### 3. Docker部署

```bash
# 1. 克隆项目
git clone <repository-url>
cd yolo8

# 2. 配置环境变量
cp .env.example .env
vim .env  # 修改配置

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f ai-detection
```

### 4. 测试场景下发

```bash
curl -X POST http://localhost:8080/api/v1/scene/deploy \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

## 📁 项目结构

```
yolo8/
├── src/                          # 源代码
│   ├── api_server.py            # API服务器
│   ├── scene_manager.py         # 场景管理器（新）
│   ├── device_platform_client.py # 设备平台客户端（新）
│   ├── heartbeat_manager.py     # 心跳管理器（新）
│   ├── kafka_publisher.py       # Kafka推送器（新）
│   ├── region_filter.py         # 区域过滤器（新）
│   ├── scene_mapper.py          # 场景映射器（新）
│   ├── detection_engine.py      # 检测引擎
│   ├── stream_manager.py        # 流管理器
│   └── config_manager.py        # 配置管理器
├── config/                       # 配置文件
│   └── default_config.yaml      # 主配置文件
├── pt_dir/                       # 模型文件目录
│   ├── fire_smoke/best.pt       # 火焰检测模型
│   ├── person/best.pt           # 人员检测模型
│   └── ...
├── nginx/                        # Nginx配置
│   └── nginx.conf               # Nginx配置文件（新）
├── docker/                       # Docker配置
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/                         # 文档
│   ├── PRODUCT_DESIGN.md        # 产品设计文档
│   └── 接入文档.md              # 接入文档
└── README.md                     # 本文档
```

## 🔧 支持的场景

| 场景名称 | 算法名称 | 检测目标 |
|---------|---------|---------|
| 明火告警 | 火焰检测 | fire, smoke |
| 人员识别 | 人员检测 | person |
| 建筑垃圾识别 | 垃圾分类 | 14类建筑垃圾 |
| 裸土识别 | 裸土检测 | luotu |

## 📖 详细文档

- [产品设计文档](docs/PRODUCT_DESIGN.md) - 完整的系统架构和接口设计
- [接入文档](docs/接入文档.md) - AI识别厂商接入规范
- [安装部署指南](docs/INSTALL.md) - 详细的安装和部署步骤

## 🐳 Docker配置说明

### 环境变量

| 变量名 | 说明 | 示例 |
|-------|------|------|
| SERVER_PUBLIC_URL | 服务器公网地址 | `http://ai.example.com` |
| DEVICE_PLATFORM_URL | 设备平台地址 | `http://192.168.1.100:8080` |
| KAFKA_BOOTSTRAP_SERVERS | Kafka地址 | `192.168.1.200:9092` |
| KAFKA_TOPIC | Kafka Topic | `event-alarm` |

### 端口说明

- `8080`: API服务端口
- `80`: Nginx服务端口（可选）

## 📝 许可证

MIT License

## 👥 联系方式

- 技术支持: support@example.com
- 项目地址: https://github.com/your-org/yolo8


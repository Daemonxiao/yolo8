# 实时视频检测系统

一个基于YOLO8的实时视频目标检测系统，支持RTSP流管理、智能报警和REST API接口。

## 🚀 功能特性

### 核心功能
- **实时视频检测**: 支持多路RTSP流的实时目标检测
- **智能报警系统**: 可配置的报警规则和多种通知方式
- **REST API接口**: 完整的HTTP API支持流管理操作
- **高性能处理**: 支持GPU加速和多线程处理
- **灵活配置**: YAML配置文件，支持热更新

### 支持的视频源
- RTSP网络摄像头流
- RTMP推流
- HTTP视频流
- 本地视频文件
- USB摄像头

### 报警通知方式
- 日志记录
- HTTP回调
- 邮件通知
- Webhook推送

## 📋 系统要求

- Python 3.8+
- CUDA 11.0+ (可选，用于GPU加速)
- 内存: 4GB+ 推荐
- 存储: 2GB+ 可用空间

## 🛠️ 安装部署

### 1. 克隆项目
```bash
git clone <repository-url>
cd yolo8
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置系统
复制并编辑配置文件:
```bash
cp config/default_config.yaml config/my_config.yaml
# 编辑 config/my_config.yaml 修改相关配置
```

### 4. 启动系统
```bash
python main.py --config config/my_config.yaml
```

## 📖 快速开始

### 启动系统
```bash
# 使用默认配置启动
python main.py

# 使用自定义配置启动
python main.py --config config/my_config.yaml

# 以守护进程模式启动
python main.py --daemon

# 查看系统状态
python main.py --status
```

### API使用示例

#### 1. 健康检查
```bash
curl http://localhost:8080/health
```

#### 2. 注册RTSP流
```bash
curl -X POST http://localhost:8080/api/v1/streams \
  -H "Content-Type: application/json" \
  -d '{
    "stream_id": "camera_001",
    "rtsp_url": "rtsp://192.168.1.100:554/stream",
    "name": "前门摄像头",
    "confidence_threshold": 0.3,
    "callback_url": "http://your-server.com/callback"
  }'
```

#### 3. 启动检测
```bash
curl -X POST http://localhost:8080/api/v1/streams/camera_001/start
```

#### 4. 获取流状态
```bash
curl http://localhost:8080/api/v1/streams/camera_001
```

#### 5. 停止检测
```bash
curl -X POST http://localhost:8080/api/v1/streams/camera_001/stop
```

#### 6. 删除流
```bash
curl -X DELETE http://localhost:8080/api/v1/streams/camera_001
```

## ⚙️ 配置说明

### 主要配置项

```yaml
# 模型配置
model:
  path: "constuction_waste/best.pt"  # 模型文件路径
  current_model: "high_accuracy"     # 当前使用的模型类型

# 检测参数
detection:
  confidence_threshold: 0.25  # 置信度阈值
  iou_threshold: 0.45        # IoU阈值
  fps_limit: 30              # 处理帧率限制
  max_streams: 10            # 最大同时处理流数量

# 报警规则
alarm:
  min_confidence: 0.5        # 最小报警置信度
  consecutive_frames: 3      # 连续检测帧数
  cooldown_seconds: 30       # 报警冷却时间

# API服务
api:
  host: "0.0.0.0"           # 服务主机
  port: 8080                # 服务端口
  debug: false              # 调试模式

# 性能配置
performance:
  use_gpu: true             # 是否使用GPU
  gpu_device: 0             # GPU设备ID
  worker_threads: 4         # 工作线程数
```

### 报警规则配置

系统支持灵活的报警规则配置：

```python
from src.alarm_system import AlarmRule, NotificationType

# 创建自定义报警规则
rule = AlarmRule(
    rule_id="high_priority",
    name="高优先级报警",
    stream_ids=["camera_001", "camera_002"],  # 指定流
    class_names=["person", "car"],            # 指定目标类别
    min_confidence=0.7,                       # 高置信度要求
    consecutive_frames=2,                     # 较少连续帧数
    cooldown_seconds=15,                      # 较短冷却时间
    time_range={"start": "08:00", "end": "18:00"},  # 工作时间
    notifications=[NotificationType.EMAIL, NotificationType.WEBHOOK]
)
```

## 🔌 API文档

### 基础接口

| 方法 | 路径 | 描述 |
|-----|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/v1/info` | 系统信息 |
| GET | `/api/v1/stats` | 统计信息 |

### 流管理接口

| 方法 | 路径 | 描述 |
|-----|------|------|
| POST | `/api/v1/streams` | 注册新流 |
| GET | `/api/v1/streams` | 获取所有流 |
| GET | `/api/v1/streams/{stream_id}` | 获取流详情 |
| PUT | `/api/v1/streams/{stream_id}/config` | 更新流配置 |
| POST | `/api/v1/streams/{stream_id}/start` | 启动检测 |
| POST | `/api/v1/streams/{stream_id}/stop` | 停止检测 |
| DELETE | `/api/v1/streams/{stream_id}` | 删除流 |

### 配置管理接口

| 方法 | 路径 | 描述 |
|-----|------|------|
| GET | `/api/v1/config` | 获取系统配置 |
| PUT | `/api/v1/config` | 更新系统配置 |

### 回调数据格式

#### 检测结果回调
```json
{
  "type": "detection",
  "stream_id": "camera_001",
  "timestamp": 1642742400.123,
  "frame_id": 1234,
  "detections": [
    {
      "id": 0,
      "class_name": "person",
      "class_id": 0,
      "confidence": 0.85,
      "bbox": [100, 50, 200, 150],
      "center": [150, 100],
      "area": 10000
    }
  ],
  "bbox_count": 1,
  "processing_time": 0.045
}
```

#### 报警事件回调
```json
{
  "type": "alarm",
  "stream_id": "camera_001",
  "timestamp": 1642742400.123,
  "alarm_type": "high",
  "confidence": 0.85,
  "bbox": [100, 50, 200, 150],
  "class_name": "person",
  "consecutive_count": 3
}
```

## 🐛 故障排除

### 常见问题

1. **模型加载失败**
   ```
   解决方案：检查模型文件路径是否正确，确保模型文件存在且可读
   ```

2. **RTSP连接失败**
   ```
   解决方案：检查网络连通性，验证RTSP URL格式，确认摄像头认证信息
   ```

3. **GPU检测失败**
   ```
   解决方案：检查CUDA安装，验证PyTorch GPU支持，检查显存是否足够
   ```

4. **API服务启动失败**
   ```
   解决方案：检查端口是否被占用，确认防火墙设置，查看日志详细信息
   ```

### 日志文件

系统日志默认保存在 `logs/detection.log`，包含详细的运行信息和错误信息。

### 性能调优

1. **GPU加速**: 确保正确安装CUDA和对应版本的PyTorch
2. **内存优化**: 根据系统内存调整缓冲区大小和工作线程数
3. **网络优化**: 调整视频流的缓冲区设置和重连策略
4. **检测优化**: 根据需求调整图像尺寸和置信度阈值

## 📄 许可证

本项目基于 MIT 许可证开源。

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📞 支持

如有问题或建议，请通过以下方式联系：
- 创建GitHub Issue
- 发送邮件至项目维护者

---

**注意**: 本项目用于学习和研究目的，在生产环境中使用请确保充分测试和安全评估。

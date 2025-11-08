# AI视频识别系统产品设计文档

## 文档信息

- **文档版本**: v1.0.0
- **创建日期**: 2024-11-08
- **最后更新**: 2024-11-08
- **产品名称**: 智能视频分析系统 (Smart Video Analytics System)
- **部署方式**: Docker 容器化部署

---

## 目录

1. [产品概述](#1-产品概述)
2. [系统架构](#2-系统架构)
3. [功能设计](#3-功能设计)
4. [接口设计](#4-接口设计)
5. [部署方案](#5-部署方案)
6. [数据流转](#6-数据流转)
7. [安全设计](#7-安全设计)
8. [性能指标](#8-性能指标)
9. [运维监控](#9-运维监控)

---

## 1. 产品概述

### 1.1 产品定位

智能视频分析系统是一个基于 YOLOv8 深度学习模型的实时视频流分析平台，支持多种检测场景，包括火灾检测、人员识别、施工安全监控等。系统采用 Docker 容器化部署，提供标准化的 RESTful API 和 Kafka 消息推送接口，便于与第三方平台快速集成。

### 1.2 核心特性

- **🎯 多场景支持**: 支持火灾检测、人员识别、高温预警、晨会监控、天气安全预警等多种检测场景
- **⚡ 实时处理**: 基于 YOLO 模型的高性能实时视频流分析
- **🔌 标准化接口**: 提供符合行业标准的 RESTful API 和 Kafka 消息队列
- **🐳 容器化部署**: 完整的 Docker 和 Docker Compose 部署方案
- **📊 灵活配置**: 支持场景下发、区域检测、时间控制等动态配置
- **💾 数据持久化**: 自动保存检测结果、告警图片和录像
- **🔄 高可用性**: 支持流断线重连、心跳保活机制

### 1.3 技术栈

- **后端框架**: Python 3.9+, Flask
- **深度学习**: PyTorch, Ultralytics YOLOv8
- **视频处理**: OpenCV
- **消息队列**: Kafka (告警推送)
- **容器化**: Docker, Docker Compose
- **配置管理**: YAML
- **数据存储**: 本地文件系统 (可扩展至 OSS)

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         外部系统                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ 监控平台     │  │ 设备管理平台  │  │ 告警接收平台  │          │
│  └──────┬───────┘  └──────┬───────┘  └──────▲───────┘          │
│         │ ①场景下发        │ ②我们调用       │ ④Kafka告警        │
│         │ (调用我们)       │ getPlayUrl      │ (我们推送)        │
│         │                  │ heartBeat       │                  │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
          │                  │                  │
┌─────────▼──────────────────▼──────────────────┼─────────────────┐
│                    Docker 容器网络                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              AI视频识别系统容器                            │   │
│  │                                                            │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │           API Server (Flask)                       │  │   │
│  │  │  【我们提供的接口】                                │  │   │
│  │  │  - POST /api/v1/scene/deploy (场景下发)           │  │   │
│  │  │  【我们调用的外部接口】                             │  │   │
│  │  │  - POST /device/getPlayUrl (获取流地址)           │  │   │
│  │  │  - POST /device/heartBeat (心跳保活)             │  │   │
│  │  │  【内部管理接口】                                  │  │   │
│  │  │  - 流管理 (启动/停止/查询)                        │  │   │
│  │  └────────────┬───────────────────────────────────────┘  │   │
│  │               │                                            │   │
│  │  ┌────────────▼───────────────────────────────────────┐  │   │
│  │  │      Stream Manager (流管理器)                      │  │   │
│  │  │  - 视频流生命周期管理                               │  │   │
│  │  │  - 心跳监控                                         │  │   │
│  │  │  - 断线重连                                         │  │   │
│  │  └────────────┬───────────────────────────────────────┘  │   │
│  │               │                                            │   │
│  │  ┌────────────▼───────────────────────────────────────┐  │   │
│  │  │     Detection Engine (检测引擎)                     │  │   │
│  │  │  - YOLO模型推理                                     │  │   │
│  │  │  - 多流并发处理                                     │  │   │
│  │  │  - 区域过滤                                         │  │   │
│  │  │  - 条件判断 (高温/晨会/天气)                        │  │   │
│  │  └────────────┬───────────────────────────────────────┘  │   │
│  │               │                                            │   │
│  │  ┌────────────▼───────────────────┬──────────────────┐   │   │
│  │  │   Alarm Handler                │  Storage Manager │   │   │
│  │  │   (告警处理)                   │  (存储管理)       │   │   │
│  │  │  - 连续帧判断                  │  - 检测结果保存   │   │   │
│  │  │  - 告警冷却                    │  - 图片保存       │   │   │
│  │  │  - Kafka推送    ───────────────┼─▶录像保存         │   │   │
│  │  └────────────────────────────────┴──────────────────┘   │   │
│  │                                                            │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              持久化存储卷                                  │   │
│  │  - /app/config     (配置文件)                             │   │
│  │  - /app/results    (检测结果)                             │   │
│  │  - /app/logs       (日志文件)                             │   │
│  │  - /app/models     (AI模型文件)                           │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘

**说明**:
- ✅ 我们的容器：AI识别服务
- ❌ 不需要部署：Kafka（使用外部Kafka）
- 📌 外部依赖：设备管理平台、Kafka服务（由对方提供）
```

### 2.2 核心组件说明

#### 2.2.1 API Server (api_server.py)
- 提供 RESTful API 接口
- 处理场景下发请求
- 管理流地址获取和心跳保活
- 实现回调机制

#### 2.2.2 Stream Manager (stream_manager.py)
- 管理多个视频流的生命周期
- 监控流状态 (active/error/reconnecting)
- 处理断线重连逻辑
- 心跳保活机制

#### 2.2.3 Detection Engine (detection_engine.py)
- 加载和管理 YOLO 模型
- 多线程并发处理视频流
- 实现区域检测过滤
- 支持自定义处理逻辑 (高温/晨会/天气预警)

#### 2.2.4 Config Manager (config_manager.py)
- 加载和管理配置文件
- 支持动态配置更新
- 场景参数管理

### 2.3 接口角色说明 ⭐

**我们的定位**: AI识别算法厂商（第三方）

**接口交互关系**:

| 交互方向 | 接口地址 | 说明 | 我们的角色 |
|---------|---------|------|-----------|
| 监控平台 → 我们 | POST /api/v1/scene/deploy | 场景下发 | **服务提供方**（我们实现此接口）|
| 我们 → 设备平台 | POST /device/getPlayUrl | 获取流地址 | **服务调用方**（我们调用外部接口）|
| 我们 → 设备平台 | POST /device/heartBeat | 心跳保活 | **服务调用方**（每10秒调用一次）|
| 我们 → Kafka | Topic: event-alarm | 告警推送 | **消息生产者**（我们推送告警）|

**工作流程**:
```
1. 监控平台调用我们的 /scene/deploy 接口，下发检测任务
2. 我们调用设备平台的 /getPlayUrl 接口，获取视频流地址
3. 我们启动检测任务，定期调用 /heartBeat 保持连接
4. 检测到告警时，我们推送消息到 Kafka
```

---

## 3. 功能设计

### 3.1 场景管理

#### 3.1.1 场景下发

**功能描述**: 接收外部平台下发的检测场景配置，包括设备信息、检测区域、算法类型、时间范围等。

**核心功能**:
- 支持多设备批量配置
- 支持多区域检测 (可配置多个多边形区域)
- 场景时间范围控制 (开始时间、结束时间)
- 算法场景映射 (火焰检测、人员识别等)

**实现逻辑**:
```python
# 场景配置流程
1. 接收场景下发请求
2. 解析设备列表和检测区域
3. 验证时间范围
4. 加载对应算法模型
5. 为每个设备创建检测任务
6. 返回配置结果
```

#### 3.1.2 支持的检测场景

| 场景名称 | 算法名称 | 检测目标 | 特殊逻辑 |
|---------|---------|---------|---------|
| 明火告警 | 火焰检测 | fire (火焰) | 连续帧检测 |
| 人员识别 | 人员检测 | person (人员) | 基础检测 |
| 高温作业预警 | 人员检测 | person | 温度条件判断 |
| 晨会未召开预警 | 人员检测 | person | 时间段+人员缺失 |
| 施工天气预警 | 通用检测 | 任意目标 | 天气条件判断 |
| 建筑垃圾识别 | 垃圾分类 | 14类建筑垃圾 | 类别过滤 |

### 3.2 视频流管理

#### 3.2.1 流地址获取（调用外部接口）

**功能描述**: 当接收到场景下发后，系统需要调用设备管理平台的接口获取视频流播放地址。

**调用方式**: 我们的系统主动调用设备管理平台接口

**调用接口**:
```python
# 我们调用外部平台
POST http://[设备平台IP]:[端口]/device/getPlayUrl
Content-Type: application/json

Request:
{
    "deviceGbCode": "31011500001320000001"
}

Response:
{
    "status": 0,
    "message": "ok",
    "data": {
        "rtsp": "rtsp://127.0.0.1:8554/stream1",
        "rtmp": "rtmp://127.0.0.1:1935/stream1",
        "hls": "http://127.0.0.1:8080/hls/stream1.m3u8",
        "flv": "http://127.0.0.1:8080/flv/stream1",
        "webrtc": "webrtc://127.0.0.1:8080/stream1"
    }
}
```

**实现逻辑**:
```python
# 内部实现
1. 接收到场景下发（包含deviceGbCode列表）
2. 遍历每个设备，调用设备平台的getPlayUrl接口
3. 获取到RTSP等流地址
4. 使用获取的流地址启动检测任务
5. 如果获取失败，记录错误并跳过该设备
```

#### 3.2.2 心跳保活（调用外部接口）

**功能描述**: 获取流地址后，需要定期向设备管理平台发送心跳，以保持流连接不过期。

**调用方式**: 我们的系统主动调用设备管理平台接口

**调用接口**:
```python
# 我们调用外部平台
POST http://[设备平台IP]:[端口]/device/heartBeat
Content-Type: application/json

Request:
{
    "deviceGbCode": "31011500001320000001"
}

Response:
{
    "status": 0,
    "message": "心跳成功"
}
```

**实现要求**:
- 心跳间隔: ≤ 10秒/次
- 自动心跳机制（后台定时任务）
- 心跳失败重试
- 超时断流处理

**心跳流程**:
```
1. 获取流地址成功后，立即启动心跳定时器
2. 每10秒向设备平台发送一次心跳请求
3. 心跳成功: 更新最后活跃时间，继续检测
4. 心跳失败: 重试3次（间隔1秒）
5. 重试失败: 标记流为错误状态，停止检测，尝试重新获取流地址
```

**心跳管理器实现**:
```python
class HeartbeatManager:
    def __init__(self, device_platform_url):
        self.platform_url = device_platform_url
        self.heartbeat_threads = {}
        
    def start_heartbeat(self, device_gb_code):
        """启动心跳线程"""
        thread = threading.Thread(
            target=self._heartbeat_worker,
            args=(device_gb_code,),
            daemon=True
        )
        self.heartbeat_threads[device_gb_code] = thread
        thread.start()
        
    def _heartbeat_worker(self, device_gb_code):
        """心跳工作线程"""
        while device_gb_code in self.heartbeat_threads:
            try:
                # 调用设备平台心跳接口
                response = requests.post(
                    f"{self.platform_url}/device/heartBeat",
                    json={"deviceGbCode": device_gb_code},
                    timeout=5
                )
                if response.json().get('status') == 0:
                    logger.info(f"设备 {device_gb_code} 心跳成功")
                else:
                    logger.warning(f"设备 {device_gb_code} 心跳失败")
            except Exception as e:
                logger.error(f"设备 {device_gb_code} 心跳异常: {e}")
            
            time.sleep(10)  # 每10秒一次
```

#### 3.2.3 断线重连

**功能描述**: 当视频流断开时自动尝试重连。

**重连策略**:
- 最大重连次数: 3次 (可配置)
- 重连间隔: 5秒 (可配置)
- 指数退避策略 (可选)
- 重连成功后恢复检测

### 3.3 检测与告警

#### 3.3.1 实时检测

**检测流程**:
```
1. 从视频流读取帧
2. 帧率控制 (默认1fps，可配置)
3. 区域过滤 (仅检测指定区域内的目标)
4. YOLO模型推理
5. 置信度过滤
6. 结果后处理
```

**区域检测**:
- 支持多边形区域定义
- 格式: `(x1,y1),(x2,y2),(x3,y3),...`
- 支持多区域: 使用 `;` 分隔
- 只保留中心点在区域内的检测结果

**性能优化**:
- 自动分辨率缩放 (大于640px时缩放)
- GPU加速 (可选)
- 多线程并发处理
- 缓冲区优化

#### 3.3.2 告警触发

**告警条件**:
- 置信度阈值: ≥ 0.5 (可配置)
- 连续帧数: ≥ 3帧 (可配置，减少误报)
- 告警冷却: 30秒 (可配置，避免频繁告警)

**告警级别**:
- **High** (高): 置信度 ≥ 0.7
- **Medium** (中): 0.5 ≤ 置信度 < 0.7
- **Low** (低): 置信度 < 0.5

**自定义告警逻辑**:

1. **高温作业预警**
   - 检测到人员 + 当前温度 ≥ 阈值 → 触发告警
   - 温度来源: 高德天气API / 固定值

2. **晨会未召开预警**
   - 工作日 + 晨会时间段 (如 08:00-08:30) + 未检测到人员 → 触发告警
   - 每天只告警一次

3. **施工天气预警**
   - 风力 ≥ 阈值 (如6级) 或 危险天气类型 (暴雨/台风) → 触发告警
   - 天气来源: 高德天气API / 固定值

#### 3.3.3 告警推送

**Kafka 消息推送**:
- Topic: `event-alarm`
- 推送内容: 场景、时间、抓拍图片、设备编码、录像地址

**推送格式**:
```json
{
    "scene": "火警",
    "alarmTime": "2024-11-08 10:04:29",
    "pic": "http://127.0.0.1:8080/results/images/alarm.jpg",
    "deviceGbCode": "31011500001320000001",
    "record": "http://127.0.0.1:8080/results/videos/alarm.mp4"
}
```

### 3.4 数据存储

#### 3.4.1 检测结果存储

**目录结构**:
```
results/
├── 2024-11-08/
│   ├── camera_001/
│   │   ├── 10-04-29-123_frame_1/
│   │   │   ├── detection_info.json    # 检测信息
│   │   │   ├── original.png           # 原始图片
│   │   │   ├── annotated.png          # 标注图片
│   │   │   └── crops/                 # 目标裁剪图
│   │   │       ├── 1_fire_0.95.png
│   │   │       └── 2_person_0.87.png
│   │   └── ...
│   └── camera_002/
│       └── ...
└── ...
```

**detection_info.json 格式**:
```json
{
    "basic_info": {
        "timestamp": "2024-11-08T10:04:29.123456",
        "stream_id": "camera_001",
        "frame_id": 1,
        "processing_time": 0.045,
        "video_source": "rtsp://..."
    },
    "stream_info": {
        "confidence_threshold": 0.5,
        "iou_threshold": 0.45,
        "fps_limit": 1
    },
    "detection_results": {
        "total_objects": 2,
        "objects": [
            {
                "id": 1,
                "class_name": "fire",
                "class_id": 0,
                "confidence": 0.95,
                "bbox": {
                    "x1": 100.5,
                    "y1": 200.3,
                    "x2": 350.8,
                    "y2": 450.2,
                    "width": 250.3,
                    "height": 249.9
                },
                "center": {"x": 225.65, "y": 325.25},
                "area": 62524.97
            }
        ]
    },
    "alarm_info": {
        "has_alarm": true,
        "alarm_level": "high",
        "alarm_objects": [
            {
                "object_id": 1,
                "class_name": "fire",
                "confidence": 0.95,
                "alarm_level": "high"
            }
        ]
    }
}
```

#### 3.4.2 存储配置

| 配置项 | 说明 | 默认值 |
|-------|------|-------|
| save_results | 是否保存检测结果 | true |
| save_images | 是否保存图片 | true |
| save_only_detections | 仅保存有检测结果的帧 | true |
| retention_days | 数据保留天数 | 30 |
| max_saved_files | 最大保存文件数 | 10000 |
| image_format | 图片格式 (png/jpg) | png |
| jpeg_quality | JPEG质量 (1-100) | 95 |
| png_compression | PNG压缩级别 (0-9) | 1 |

---

## 4. 接口设计

### 4.1 我们需要提供的接口（供外部平台调用）

#### 4.1.1 场景下发接口 ⭐

**接口说明**: 外部平台通过此接口向我们下发检测场景配置。

**接口地址**: `POST http://[我们的IP]:[端口]/api/v1/scene/deploy`

**请求方式**: POST

**请求头**:
```
Content-Type: application/json
X-API-Key: your-api-key  # API密钥认证
```

**请求参数**:

| 参数 | 必选 | 类型 | 说明 |
|------|------|------|------|
| devices | true | array | 设备列表 |
| -deviceGbCode | true | string | 设备国标编码 |
| -area | true | string | 检测区域坐标，格式：(x1,y1),(x2,y2),... 多区域用;分隔 |
| scene | true | string | 场景名称，如"明火告警" |
| algorithm | true | string | 算法名称，如"火焰检测" |
| startDate | true | string | 场景启动时间，格式：yyyy-MM-dd HH:mm:ss |
| endDate | true | string | 场景结束时间，格式：yyyy-MM-dd HH:mm:ss |

**请求示例**:
```json
{
    "devices": [
        {
            "deviceGbCode": "31011500001320000001",
            "area": "(100,100),(500,100),(500,400),(100,400)"
        },
        {
            "deviceGbCode": "31011500001320000002",
            "area": "(100,100),(200,100),(200,200),(100,200);(300,300),(400,300),(400,400),(300,400)"
        }
    ],
    "scene": "明火告警",
    "algorithm": "火焰检测",
    "startDate": "2024-06-01 10:00:00",
    "endDate": "2025-06-01 10:00:00"
}
```

**返回字段**:

| 返回字段 | 字段类型 | 说明 |
|----------|----------|------|
| status | int | 返回结果状态。0：正常；1：错误。 |
| message | string | 返回说明 |
| data | object | 返回数据（可选）|
| -deployed_devices | int | 成功部署的设备数 |
| -failed_devices | int | 失败的设备数 |
| -failed_list | array | 失败设备列表（含失败原因）|

**返回示例**:
```json
{
    "status": 0,
    "message": "场景部署成功",
    "data": {
        "deployed_devices": 2,
        "failed_devices": 0,
        "failed_list": []
    }
}
```

**处理流程**:
```
1. 接收场景下发请求
2. 验证请求参数（场景、时间范围等）
3. 遍历设备列表
4. 对每个设备：
   4.1 调用设备平台 /device/getPlayUrl 获取流地址
   4.2 解析检测区域坐标
   4.3 根据算法类型加载对应模型
   4.4 启动检测任务
   4.5 启动心跳保活线程
5. 返回部署结果
```

### 4.2 我们需要调用的外部接口

#### 4.2.1 获取设备播放地址

**接口说明**: 根据设备国标编码获取视频流地址。

**接口地址**: `POST http://[设备平台IP]:[端口]/device/getPlayUrl`

**调用方**: 我们的系统

**请求参数**:
```json
{
    "deviceGbCode": "31011500001320000001"
}
```

**返回数据**:
```json
{
    "status": 0,
    "message": "ok",
    "data": {
        "rtsp": "rtsp://127.0.0.1:8554/stream1",
        "rtmp": "rtmp://127.0.0.1:1935/stream1",
        "hls": "http://127.0.0.1:8080/hls/stream1.m3u8",
        "flv": "http://127.0.0.1:8080/flv/stream1",
        "webrtc": "webrtc://127.0.0.1:8080/stream1"
    }
}
```

**使用场景**: 接收到场景下发后，根据deviceGbCode调用此接口获取流地址。

#### 4.2.2 设备心跳保活

**接口说明**: 保持设备流连接活跃。

**接口地址**: `POST http://[设备平台IP]:[端口]/device/heartBeat`

**调用方**: 我们的系统

**调用频率**: 每10秒一次

**请求参数**:
```json
{
    "deviceGbCode": "31011500001320000001"
}
```

**返回数据**:
```json
{
    "status": 0,
    "message": "心跳成功"
}
```

**使用场景**: 获取流地址后，后台定时调用此接口保持连接。

### 4.3 告警推送（Kafka）

**推送方式**: 我们的系统通过 Kafka 推送告警消息

**Topic**: `event-alarm`

**消息格式**:

| 参数 | 必选 | 类型 | 说明 |
|------|------|------|------|
| scene | true | string | 事件告警场景，如"火警" |
| alarmTime | true | string | 事件告警时间，格式：yyyy-MM-dd HH:mm:ss |
| pic | true | string | 告警抓拍图片URL |
| deviceGbCode | true | string | 设备国标编码 |
| record | true | string | 告警录像地址URL |

**消息示例**:
```json
{
    "scene": "火警",
    "alarmTime": "2024-11-08 10:04:29",
    "pic": "http://ai.example.com/results/images/2024-11-08/camera_001/10-04-29-123_frame_1/annotated.png",
    "deviceGbCode": "31011500001320000001",
    "record": "http://ai.example.com/results/videos/camera_001_20241108_100429.mp4"
}
```

**URL配置说明** ⭐:
- `pic` 和 `record` 字段需要包含完整的可访问URL
- URL格式：`http://{SERVER_URL}/results/...`
- `SERVER_URL` 需要在配置文件中设置为我们服务器的公网地址

**推送时机**: 
- 满足告警条件时（连续N帧检测到目标且置信度超过阈值）
- 自定义告警逻辑触发时（高温预警、晨会预警、天气预警等）

**图片/录像访问**:
- 需要通过Nginx暴露 `/results` 目录
- 确保外部平台能访问我们的服务器（防火墙/安全组开放端口）
- 建议使用域名而非IP（便于迁移）

### 4.4 内部管理接口（可选，用于运维）

#### 4.3.1 启动检测流

```
POST /api/v1/streams/start
Content-Type: application/json

Request Body:
{
    "stream_id": "camera_001",
    "rtsp_url": "rtsp://127.0.0.1:8554/stream1",
    "name": "监控点01",
    "detection_callback": "http://callback-server/detection",
    "alarm_callback": "http://callback-server/alarm"
}

Response:
{
    "success": true,
    "message": "视频流启动成功",
    "data": {
        "stream_id": "camera_001",
        "status": "active"
    }
}
```

#### 4.3.2 停止检测流

```
POST /api/v1/streams/stop
Content-Type: application/json

Request Body:
{
    "stream_id": "camera_001"
}

Response:
{
    "success": true,
    "message": "视频流已停止"
}
```

#### 4.3.3 查询流状态

```
GET /api/v1/streams/info?stream_id=camera_001

Response:
{
    "success": true,
    "data": {
        "streams": [
            {
                "stream_id": "camera_001",
                "name": "监控点01",
                "rtsp_url": "rtsp://...",
                "status": "active",
                "frame_count": 1250,
                "detection_count": 35,
                "error_count": 0,
                "created_time": 1699420800.0,
                "last_active_time": 1699424400.0
            }
        ],
        "total": 1
    }
}
```

### 4.4 Kafka 告警推送

**Topic**: `event-alarm`

**消息格式**:
```json
{
    "scene": "火警",
    "alarmTime": "2024-11-08 10:04:29",
    "pic": "http://server-ip:8080/results/2024-11-08/camera_001/10-04-29-123_frame_1/annotated.png",
    "deviceGbCode": "31011500001320000001",
    "record": "http://server-ip:8080/results/videos/camera_001_20241108_100429.mp4"
}
```

---

## 5. 部署方案

### 5.1 Docker 容器化部署

#### 5.1.1 Dockerfile

```dockerfile
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/logs /app/results /app/results/images /app/config

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

# 启动命令
CMD ["python", "main.py"]
```

#### 5.1.2 docker-compose.yml

```yaml
version: '3.8'

services:
  # AI识别服务
  ai-detection:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ai-detection-service
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      # 配置文件
      - ./config:/app/config
      # 模型文件
      - ./models:/app/models
      # 检测结果持久化
      - ./data/results:/app/results
      # 日志持久化
      - ./data/logs:/app/logs
    environment:
      - TZ=Asia/Shanghai
      - PYTHONUNBUFFERED=1
      - LOG_LEVEL=INFO
      # 服务器配置（必须配置）⭐
      - SERVER_PUBLIC_URL=http://ai.example.com  # 用于生成告警图片URL
      # 外部Kafka配置（必须配置）⭐
      - KAFKA_BOOTSTRAP_SERVERS=外部Kafka地址:9092
      - KAFKA_TOPIC=event-alarm
      # 设备平台配置（必须配置）⭐
      - DEVICE_PLATFORM_URL=http://设备平台IP:端口
      - DEVICE_PLATFORM_TIMEOUT=10
      # API认证（可选）
      - API_KEY=your-secret-api-key
    networks:
      - ai-network
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G

  # Nginx (可选，用于静态文件服务)
  nginx:
    image: nginx:alpine
    container_name: nginx-proxy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./data/results:/usr/share/nginx/html/results:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    networks:
      - ai-network
    depends_on:
      - ai-detection

networks:
  ai-network:
    driver: bridge
```

**重要说明**:
- ❌ **不需要部署Kafka**: 我们只是Kafka的生产者，连接外部已有的Kafka
- ⚠️ **必须配置**: `KAFKA_BOOTSTRAP_SERVERS` 指向外部Kafka地址
- ⚠️ **必须配置**: `DEVICE_PLATFORM_URL` 指向设备管理平台地址
- 📝 **简化部署**: 只需要部署AI识别服务和Nginx（可选）

### 5.2 部署步骤

#### 5.2.1 部署前检查清单 ⭐

在开始部署前，请确认以下配置和依赖已就绪：

| 检查项 | 说明 | 示例值 |
|-------|------|-------|
| ✅ 服务器公网地址 | 用于生成告警图片URL，外部平台需能访问 | `http://ai.example.com` 或 `http://123.45.67.89:8080` |
| ✅ 设备管理平台地址 | 提供 `/device/getPlayUrl` 和 `/device/heartBeat` 接口 | `http://192.168.1.100:8080` |
| ✅ Kafka服务地址 | 外部Kafka集群地址 | `192.168.1.200:9092` |
| ✅ Kafka Topic | 确认Topic已创建或可自动创建 | `event-alarm` |
| ✅ 网络连通性 | 确保我们的服务能访问设备平台和Kafka | - |
| ✅ 外部访问权限 | 确保外部平台能访问我们的服务器（防火墙/安全组开放80或8080端口）| - |
| ✅ AI模型文件 | 准备好训练的 .pt 模型文件 | `models/best.pt` |
| ✅ 域名解析（可选）| 如果使用域名，确保DNS解析配置正确 | `ai.example.com` → 服务器IP |

#### 5.2.2 环境准备

```bash
# 1. 安装 Docker 和 Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 2. 克隆项目
git clone <repository-url>
cd yolo8

# 3. 准备模型文件
# 将训练好的 .pt 模型文件放到 models/ 目录
mkdir -p models
cp your_model.pt models/

# 4. 配置文件准备
# 编辑 config/default_config.yaml，配置外部依赖地址
vim config/default_config.yaml

# 重点配置：
# - server.public_url: 服务器公网地址（用于生成告警图片URL）
# - device_platform.base_url: 设备管理平台地址
# - kafka.bootstrap_servers: 外部Kafka地址
# - kafka.topic: event-alarm

# 5. 配置Nginx（如果使用）
mkdir -p nginx
cat > nginx/nginx.conf << 'EOF'
server {
    listen 80;
    server_name ai.example.com;  # 修改为你的域名或IP
    
    # 静态文件服务 - 提供告警图片访问
    location /results/ {
        alias /usr/share/nginx/html/results/;
        autoindex off;
        add_header Access-Control-Allow-Origin *;
    }
    
    # API代理
    location /api/ {
        proxy_pass http://ai-detection:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF
```

#### 5.2.3 启动服务

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f ai-detection

# 停止服务
docker-compose down

# 重启服务
docker-compose restart ai-detection
```

#### 5.2.4 验证部署

```bash
# 1. 健康检查
curl http://localhost:8080/api/v1/health

# 2. 查询流列表
curl http://localhost:8080/api/v1/streams/info

# 3. 测试场景下发接口
curl -X POST http://localhost:8080/api/v1/scene/deploy \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
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

# 4. 查看日志，确认是否成功调用设备平台接口
docker-compose logs -f ai-detection | grep "getPlayUrl"
docker-compose logs -f ai-detection | grep "heartBeat"

# 5. 验证Kafka推送（在外部Kafka消费者端验证）
# 当有告警时，外部Kafka应该能收到 event-alarm topic 的消息
```

### 5.3 配置管理

#### 5.3.1 核心配置文件

**config/default_config.yaml**:
```yaml
# 模型配置
model:
  path: "models/best.pt"

# 检测参数
detection:
  confidence_threshold: 0.5
  iou_threshold: 0.45
  image_size: 640
  fps_limit: 1
  max_streams: 10
  auto_resize: true
  max_resolution: 640

# 报警配置
alarm:
  min_confidence: 0.5
  consecutive_frames: 3
  cooldown_seconds: 30
  levels:
    low: 0.3
    medium: 0.5
    high: 0.7

# API配置
api:
  port: 8080
  host: "0.0.0.0"
  version: "v1"
  debug: false

# 服务器配置（重要！用于生成告警图片/录像URL）⭐
server:
  # 服务器公网地址或域名，用于生成可访问的URL
  # 外部平台将通过此URL访问告警图片和录像
  public_url: "http://ai.example.com"  # 或 "http://123.45.67.89:8080"
  # 如果使用Nginx代理，配置Nginx监听的端口
  nginx_port: 80  # 或 443 (HTTPS)

# 设备平台配置（重要！必须配置）⭐
device_platform:
  base_url: "http://192.168.1.100:8080"  # 设备管理平台地址
  timeout: 10  # 接口调用超时时间（秒）
  retry_times: 3  # 失败重试次数

# Kafka配置（重要！必须配置）⭐
kafka:
  bootstrap_servers: "192.168.1.200:9092"  # 外部Kafka地址
  topic: "event-alarm"  # 告警推送Topic
  enabled: true  # 是否启用Kafka推送

# 存储配置
storage:
  save_results: true
  save_images: true
  results_path: "results/"
  images_path: "results/images/"
  retention_days: 30
  image_format: "png"
  jpeg_quality: 95
```

#### 5.3.2 场景配置

可以为不同场景创建专用配置文件：

- `config/fire_detection_config.yaml` - 火灾检测
- `config/person_detection_config.yaml` - 人员识别
- `config/high_temp_config.yaml` - 高温预警
- `config/morning_meeting_config.yaml` - 晨会监控
- `config/weather_safety_config.yaml` - 天气预警

### 5.4 扩展部署

#### 5.4.1 多实例部署 (负载均衡)

```yaml
services:
  ai-detection:
    # ... (同上)
    deploy:
      replicas: 3  # 启动3个实例

  nginx:
    # ... 配置负载均衡
```

#### 5.4.2 GPU 加速部署

```yaml
services:
  ai-detection:
    # ... (同上)
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

---

## 6. 数据流转

### 6.1 场景部署流程

```
监控平台               AI识别系统（我们）              设备管理平台
    │                       │                              │
    │ 1. POST /scene/deploy │                              │
    ├──────────────────────▶│                              │
    │ {devices, scene,...}  │                              │
    │                       │                              │
    │                       │ 2. 遍历设备列表               │
    │                       │ FOR each device:             │
    │                       │                              │
    │                       │ 3. POST /device/getPlayUrl   │
    │                       ├─────────────────────────────▶│
    │                       │ {deviceGbCode}               │
    │                       │                              │
    │                       │ 4. 返回流地址                 │
    │                       │◀─────────────────────────────┤
    │                       │ {rtsp, rtmp, hls, ...}       │
    │                       │                              │
    │                       │ 5. 解析检测区域               │
    │                       │    加载对应算法模型           │
    │                       │                              │
    │                       │ 6. 启动检测任务               │
    │                       │    - 创建检测线程             │
    │                       │    - 连接视频流               │
    │                       │    - 初始化YOLO推理           │
    │                       │                              │
    │                       │ 7. 启动心跳保活线程           │
    │                       │    (每10秒调用一次心跳接口)    │
    │                       │                              │
    │ 8. 返回部署结果        │                              │
    │◀──────────────────────┤                              │
    │ {status: 0,           │                              │
    │  deployed: 2}         │                              │
    │                       │                              │
```

**关键点**:
1. **我们的角色**: AI识别厂商，接收监控平台的场景下发
2. **我们提供**: `/api/v1/scene/deploy` 接口
3. **我们调用**: 设备平台的 `/device/getPlayUrl` 和 `/device/heartBeat` 接口
4. **我们推送**: Kafka 告警消息到 `event-alarm` Topic

### 6.2 实时检测流程

```
视频流源              AI识别系统                    告警接收平台
    │                    │                              │
    │  1. RTSP视频帧     │                              │
    ├───────────────────▶│                              │
    │                    │  2. 帧预处理                 │
    │                    │  - 区域过滤                  │
    │                    │  - 缩放调整                  │
    │                    │                              │
    │                    │  3. YOLO推理                 │
    │                    │  - 目标检测                  │
    │                    │  - 置信度过滤                │
    │                    │                              │
    │                    │  4. 后处理                   │
    │                    │  - 连续帧判断                │
    │                    │  - 告警冷却                  │
    │                    │  - 自定义逻辑                │
    │                    │                              │
    │                    │  5. 保存结果                 │
    │                    │  - 检测信息JSON              │
    │                    │  - 原始图片                  │
    │                    │  - 标注图片                  │
    │                    │                              │
    │                    │  6. Kafka推送告警            │
    │                    ├─────────────────────────────▶│
    │                    │  {scene, pic, record, ...}   │
    │                    │                              │
```

### 6.3 心跳保活流程

```
AI识别系统（我们）        设备管理平台
    │                        │
    │ [后台心跳线程]          │
    │  定时器 (每10秒)        │
    │────┐                   │
    │    │ 触发               │
    │◀───┘                   │
    │                        │
    │ POST /device/heartBeat │
    ├───────────────────────▶│
    │ {deviceGbCode}         │
    │                        │
    │ {status: 0}            │
    │◀───────────────────────┤
    │                        │
    │ 记录心跳成功            │
    │ 更新最后活跃时间        │
    │                        │
    │ [10秒后]               │
    │────┐                   │
    │    │ 再次触发            │
    │◀───┘                   │
    │                        │
    │ POST /device/heartBeat │
    ├───────────────────────▶│
    │ ...循环...             │
    │                        │
```

**说明**:
- 每个设备启动检测后，自动创建独立的心跳线程
- 心跳失败超过3次后，标记流为异常状态
- 异常状态下，停止检测并尝试重新获取流地址

---

## 7. 安全设计

### 7.1 接口安全

#### 7.1.1 认证机制

- **API Key**: 每个请求携带API密钥
- **JWT Token**: 基于令牌的身份验证
- **IP白名单**: 限制访问来源

```python
# 示例：API Key认证
headers = {
    "X-API-Key": "your-api-key-here",
    "Content-Type": "application/json"
}
```

#### 7.1.2 HTTPS加密

```yaml
# nginx SSL配置
server {
    listen 443 ssl http2;
    server_name ai-detection.example.com;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
}
```

### 7.2 数据安全

#### 7.2.1 敏感信息加密

- 配置文件中的API密钥使用环境变量
- 数据库密码加密存储
- 流地址不记录到日志

#### 7.2.2 访问控制

```yaml
# 文件权限设置
- config/: 600 (仅owner可读写)
- logs/: 644 (owner读写，其他只读)
- results/: 755 (所有人可读，owner可写)
```

### 7.3 容器安全

```yaml
# docker-compose.yml 安全配置
services:
  ai-detection:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    user: "1000:1000"  # 非root用户运行
```

---

## 8. 性能指标

### 8.1 处理能力

| 指标 | 目标值 | 说明 |
|-----|-------|------|
| 单流处理帧率 | 1-5 FPS | 可配置，平衡实时性和资源消耗 |
| 并发视频流数量 | 10-50 路 | 取决于硬件配置和模型复杂度 |
| 单帧推理时间 | < 100ms | YOLO模型推理时间 |
| 告警响应时间 | < 1s | 从检测到推送的总时间 |
| API响应时间 | < 200ms | 接口平均响应时间 |

### 8.2 资源消耗

#### 8.2.1 CPU模式

- **单流**: 1 CPU核心，2GB内存
- **10路流**: 4 CPU核心，8GB内存
- **50路流**: 16 CPU核心，32GB内存

#### 8.2.2 GPU模式

- **单流**: 0.2 GPU (约2GB显存)
- **10路流**: 1 GPU (8-10GB显存)
- **50路流**: 2-3 GPU (16-24GB显存)

### 8.3 存储需求

| 场景 | 每路流/天 | 说明 |
|-----|----------|------|
| 仅保存告警 (1次/小时) | ~100MB | JSON + 图片 |
| 保存所有检测 (1fps) | ~5GB | JSON + 图片 |
| 包含录像 (1分钟/次) | ~20GB | JSON + 图片 + 视频 |

**建议**:
- 使用SSD存储以提高I/O性能
- 配置数据保留策略 (默认30天)
- 定期清理或归档历史数据
- 考虑对象存储 (OSS/S3) 用于长期保存

### 8.4 网络带宽

| 流格式 | 分辨率 | 码率 | 10路流总带宽 |
|-------|-------|------|-------------|
| RTSP (H.264) | 1920x1080 | 2-4 Mbps | 20-40 Mbps |
| RTSP (H.265) | 1920x1080 | 1-2 Mbps | 10-20 Mbps |
| RTMP | 1920x1080 | 2-5 Mbps | 20-50 Mbps |

**建议**: 预留至少 2倍的带宽余量

---

## 9. 运维监控

### 9.1 健康检查

```python
# GET /api/v1/health
{
    "status": "healthy",
    "timestamp": "2024-11-08T10:00:00",
    "version": "v1.0.0",
    "uptime": 3600,
    "services": {
        "detection_engine": "running",
        "kafka": "connected",
        "model": "loaded"
    }
}
```

### 9.2 监控指标

#### 9.2.1 系统指标

- CPU使用率
- 内存使用率
- GPU使用率 (如果使用)
- 磁盘使用率
- 网络I/O

#### 9.2.2 业务指标

```python
# GET /api/v1/stats
{
    "active_streams": 10,
    "total_frames_processed": 125000,
    "total_detections": 3500,
    "total_alarms": 85,
    "average_fps": 1.2,
    "average_processing_time": 0.045,
    "error_rate": 0.001
}
```

### 9.3 日志管理

#### 9.3.1 日志级别

- **DEBUG**: 详细的调试信息
- **INFO**: 正常运行信息
- **WARNING**: 警告信息（如重连、心跳失败）
- **ERROR**: 错误信息（如模型加载失败）
- **CRITICAL**: 严重错误（如系统崩溃）

#### 9.3.2 日志格式

```
2024-11-08 10:04:29,123 - src.detection_engine - INFO - 流 camera_001 已处理 100 帧, 检测耗时: 0.045s
2024-11-08 10:04:30,456 - src.alarm_handler - WARNING - 触发告警: 流ID=camera_001, 类型=high, 目标=fire
2024-11-08 10:04:31,789 - src.stream_manager - ERROR - 视频流断开: camera_002, 开始重连...
```

#### 9.3.3 日志轮转

```yaml
# logging配置
logging:
  level: "INFO"
  file_path: "logs/detection.log"
  max_file_size: 100  # MB
  backup_count: 5
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

### 9.4 告警通知

#### 9.4.1 系统告警

- 服务异常告警
- 资源使用率告警 (CPU > 80%, 内存 > 90%)
- 磁盘空间告警 (< 10%)
- 流断开告警 (超过最大重连次数)

#### 9.4.2 通知方式

- 邮件通知
- 短信通知
- 企业微信/钉钉
- Webhook回调

### 9.5 故障排查

#### 9.5.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|-----|---------|---------|
| 流无法连接 | RTSP地址错误、网络不通 | 检查URL、网络连接 |
| 检测延迟高 | CPU/GPU资源不足 | 降低并发流数、升级硬件 |
| 告警不推送 | Kafka未连接 | 检查Kafka服务、网络 |
| 图片模糊 | 视频流质量差 | 调整捕获分辨率、编码格式 |
| 内存泄漏 | 资源未释放 | 重启服务、检查代码 |

#### 9.5.2 诊断命令

```bash
# 查看容器日志
docker-compose logs -f ai-detection

# 进入容器
docker exec -it ai-detection-service bash

# 检查进程
ps aux | grep python

# 检查端口
netstat -tlnp | grep 8080

# 检查磁盘空间
df -h

# 检查内存
free -h

# 查看GPU使用 (如果使用GPU)
nvidia-smi
```

---

## 10. 附录

### 10.1 算法场景映射表

| 场景名称 | 算法名称 | 模型文件 | 检测类别 | 特殊逻辑 |
|---------|---------|---------|---------|---------|
| 明火告警 | 火焰检测 | fire_detection.pt | fire | 连续帧+冷却 |
| 人员识别 | 人员检测 | person_detection.pt | person | 基础检测 |
| 高温作业预警 | 人员检测 | person_detection.pt | person | 温度条件 |
| 晨会未召开预警 | 人员检测 | person_detection.pt | person | 时间+人员 |
| 施工天气预警 | 通用检测 | general.pt | 任意 | 天气条件 |
| 安全帽检测 | 安全帽检测 | helmet.pt | person, helmet | 关联检测 |
| 反光衣检测 | 反光衣检测 | vest.pt | person, vest | 关联检测 |
| 建筑垃圾分类 | 垃圾分类 | construction_waste.pt | 14类垃圾 | 类别过滤 |

### 10.2 区域坐标格式

#### 10.2.1 单区域

```
格式: (x1,y1),(x2,y2),(x3,y3),(x4,y4)
示例: (100,100),(500,100),(500,400),(100,400)
说明: 定义一个矩形区域，左上角(100,100)，右下角(500,400)
```

#### 10.2.2 多区域

```
格式: 区域1;区域2;区域3
示例: (100,100),(200,100),(200,200),(100,200);(300,300),(400,300),(400,400),(300,400)
说明: 使用分号分隔多个区域
```

#### 10.2.3 不规则多边形

```
格式: (x1,y1),(x2,y2),...,(xn,yn)
示例: (100,100),(200,150),(250,300),(150,350),(50,250)
说明: 定义一个5边形区域
```

### 10.3 环境变量配置

```bash
# .env 文件示例
TZ=Asia/Shanghai
PYTHONUNBUFFERED=1
LOG_LEVEL=INFO

# 服务器配置（重要！必须配置）⭐
SERVER_PUBLIC_URL=http://ai.example.com  # 或 http://公网IP:端口
# 示例：
# - 使用域名: http://ai-detection.company.com
# - 使用公网IP: http://123.45.67.89:8080
# - 使用Nginx: http://ai.example.com (默认80端口)

# 设备平台配置（重要！必须配置）⭐
DEVICE_PLATFORM_URL=http://192.168.1.100:8080  # 设备管理平台地址
DEVICE_PLATFORM_TIMEOUT=10
DEVICE_PLATFORM_RETRY=3

# Kafka配置（重要！必须配置）⭐
KAFKA_BOOTSTRAP_SERVERS=192.168.1.200:9092  # 外部Kafka地址
KAFKA_TOPIC=event-alarm

# 高德天气API（可选，用于高温/天气预警场景）
GAODE_API_KEY=your-api-key
GAODE_CITY=310000

# 性能配置
MAX_WORKERS=4
MAX_STREAMS=10
USE_GPU=false

# 存储配置
RESULTS_PATH=/app/results
RETENTION_DAYS=30

# API认证（可选）
API_KEY=your-secret-api-key
```

### 10.4 快速启动脚本

```bash
#!/bin/bash
# scripts/quick_start.sh

echo "🚀 启动AI视频识别系统..."

# 1. 检查Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 请先安装Docker"
    exit 1
fi

# 2. 创建必要目录
mkdir -p data/{results,logs} models config

# 3. 检查模型文件
if [ ! -f "models/best.pt" ]; then
    echo "⚠️  未找到模型文件，请将模型放到 models/ 目录"
    exit 1
fi

# 4. 启动服务
docker-compose up -d

# 5. 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 6. 健康检查
if curl -s http://localhost:8080/api/v1/health | grep -q "healthy"; then
    echo "✅ 服务启动成功！"
    echo "📝 API地址: http://localhost:8080"
    echo "📊 查看日志: docker-compose logs -f"
else
    echo "❌ 服务启动失败，请检查日志"
    docker-compose logs
fi
```

### 10.5 参考文档

- [YOLOv8 官方文档](https://docs.ultralytics.com/)
- [OpenCV 文档](https://docs.opencv.org/)
- [Docker 文档](https://docs.docker.com/)
- [Kafka 文档](https://kafka.apache.org/documentation/)
- [高德开放平台](https://lbs.amap.com/)

---

## 文档结束

**版本历史**:
- v1.0.0 (2024-11-08): 初始版本发布

**联系方式**:
- 技术支持: support@example.com
- 项目地址: https://github.com/your-org/ai-detection

**许可证**: MIT License


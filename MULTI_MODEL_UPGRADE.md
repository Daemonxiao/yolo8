# 🚀 多模型支持升级说明

## 📋 升级内容

系统已升级为支持多模型管理，可以同时加载多个YOLO模型，每个场景使用对应的模型。

## ✨ 新功能

### 1. 模型管理器 (`src/model_manager.py`)

新增全局模型管理器，负责：
- ✅ 多模型加载和缓存
- ✅ 自动设备检测（GPU/MPS/CPU）
- ✅ 按需加载模型
- ✅ 模型信息查询

**使用示例：**
```python
from src.model_manager import model_manager

# 加载模型
model_manager.load_model("pt_dir/fire_smoke/best.pt")

# 获取模型
model = model_manager.get_model("pt_dir/fire_smoke/best.pt")

# 查看已加载的模型
models = model_manager.get_loaded_models()
```

### 2. 配置文件更新

`config/default_config.yaml` 新增多模型配置：

```yaml
model:
  # 默认模型（兼容旧代码）
  path: "pt_dir/constuction_waste/constuction_waste/best.pt"
  
  # 多模型配置
  scene_models:
    "火灾检测": "pt_dir/fire_smoke/best.pt"
    "人员检测": "pt_dir/person/best.pt"
    "建筑垃圾识别": "pt_dir/constuction_waste/constuction_waste/best.pt"
    "裸土识别": "pt_dir/luotu/best.pt"
  
  # 是否在启动时预加载所有模型
  preload_all: true
```

### 3. 系统启动时预加载

系统启动时会自动预加载配置中的所有模型：

```
INFO - 预加载AI模型...
INFO - 模型预加载完成: 4/4 个模型可用
INFO -   ✓ 火灾检测: pt_dir/fire_smoke/best.pt
INFO -   ✓ 人员检测: pt_dir/person/best.pt
INFO -   ✓ 建筑垃圾识别: pt_dir/constuction_waste/constuction_waste/best.pt
INFO -   ✓ 裸土识别: pt_dir/luotu/best.pt
```

### 4. 场景下发自动选择模型

场景下发时，系统会根据场景名称自动选择对应的模型：

```json
{
  "scene": "火灾检测",
  "algorithm": "火焰检测",
  "devices": [...]
}
```

系统会自动使用 `pt_dir/fire_smoke/best.pt` 模型。

## 🔄 API变化

### StreamConfig 新增字段

```python
@dataclass
class StreamConfig:
    # ... 原有字段 ...
    model_path: str = ""  # 指定使用的模型路径（可选）
```

### DetectionEngine.start_detection 新增参数

```python
def start_detection(
    self, 
    stream_id: str, 
    video_source: str,
    custom_params: Optional[Dict] = None,
    model_path: Optional[str] = None  # 新增：指定模型路径
) -> bool:
```

## 📊 性能优化

### 模型缓存机制

- 模型加载后会缓存在内存中
- 多个流使用同一个模型时，只加载一次
- 节省内存和启动时间

### 预加载策略

**优点：**
- ✅ 启动时一次性加载，后续无需等待
- ✅ 场景切换无延迟
- ✅ 适合固定场景的生产环境

**配置：**
```yaml
model:
  preload_all: true  # 启用预加载
```

## 🎯 使用场景

### 场景1：固定场景（推荐）

配置文件中定义所有需要的场景和模型，系统启动时预加载：

```yaml
model:
  preload_all: true
  scene_models:
    "火灾检测": "pt_dir/fire_smoke/best.pt"
    "人员检测": "pt_dir/person/best.pt"
```

### 场景2：动态加载

需要时才加载模型：

```yaml
model:
  preload_all: false
```

模型会在第一次使用时自动加载。

### 场景3：指定模型

通过API直接指定模型：

```python
stream_config = StreamConfig(
    stream_id="camera_001",
    rtsp_url="rtsp://...",
    model_path="pt_dir/fire_smoke/best.pt"  # 明确指定模型
)
```

## 🔍 模型管理

### 查看已加载的模型

```bash
curl http://localhost:8080/api/v1/models
```

返回：
```json
{
  "success": true,
  "data": {
    "models": {
      "pt_dir/fire_smoke/best.pt": {
        "path": "pt_dir/fire_smoke/best.pt",
        "classes": {0: "fire", 1: "smoke"},
        "num_classes": 2,
        "device": "cpu"
      },
      ...
    }
  }
}
```

## 📝 配置示例

### 最小配置

```yaml
model:
  path: "pt_dir/person/best.pt"  # 默认模型
  preload_all: false
```

### 完整配置

```yaml
model:
  # 默认模型
  path: "pt_dir/constuction_waste/constuction_waste/best.pt"
  
  # 场景模型映射
  scene_models:
    "火灾检测": "pt_dir/fire_smoke/best.pt"
    "人员检测": "pt_dir/person/best.pt"
    "建筑垃圾识别": "pt_dir/constuction_waste/constuction_waste/best.pt"
    "裸土识别": "pt_dir/luotu/best.pt"
    "高温作业预警": "pt_dir/person/best.pt"
    "晨会未召开预警": "pt_dir/person/best.pt"
  
  # 启动时预加载所有模型
  preload_all: true
```

## 🚀 升级步骤

### 1. 更新代码

所有代码已自动更新，无需手动修改。

### 2. 更新配置

编辑 `config/default_config.yaml`，添加 `scene_models` 配置。

### 3. 重启服务

```bash
cd docker
docker-compose restart ai-detection
```

### 4. 验证

查看日志确认所有模型加载成功：

```bash
docker-compose logs ai-detection | grep "模型"
```

应该看到：
```
INFO - 模型预加载完成: 4/4 个模型可用
INFO -   ✓ 火灾检测: pt_dir/fire_smoke/best.pt
INFO -   ✓ 人员检测: pt_dir/person/best.pt
INFO -   ✓ 建筑垃圾识别: pt_dir/constuction_waste/constuction_waste/best.pt
INFO -   ✓ 裸土识别: pt_dir/luotu/best.pt
```

## 🎉 优势

1. **灵活性** - 支持多个场景，每个场景使用最合适的模型
2. **性能** - 模型预加载，场景切换无延迟
3. **可扩展** - 轻松添加新的场景和模型
4. **向后兼容** - 保留单模型模式，不影响现有功能
5. **内存优化** - 模型缓存机制，避免重复加载

## 📚 相关文档

- **模型管理器API**: `src/model_manager.py`
- **配置说明**: `config/default_config.yaml`
- **场景映射**: `src/scene_mapper.py`
- **部署指南**: `DEPLOY_GUIDE.md`

---

**升级完成！** 🎊

现在系统支持多模型并发检测，可以同时处理不同场景的视频流了。


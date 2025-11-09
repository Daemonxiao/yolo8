# 🎯 算法模型映射说明

## 📋 设计理念

**简单直接**：场景下发时，**只关注算法名称**，忽略场景字段。

- ✅ 一个算法对应一个模型
- ✅ 所有映射通过配置文件管理
- ✅ 配置即用，无需修改代码

## 🔧 配置方式

### 配置文件：`config/default_config.yaml`

```yaml
model:
  # 默认模型（当算法未配置时使用）
  default: "pt_dir/person/best.pt"
  
  # 算法名称 -> 模型路径映射
  algorithm_models:
    "火焰检测": "pt_dir/fire_smoke/best.pt"
    "人员检测": "pt_dir/person/best.pt"
    "垃圾分类": "pt_dir/constuction_waste/constuction_waste/best.pt"
    "裸土检测": "pt_dir/luotu/best.pt"
  
  # 算法目标类别过滤（可选）
  # 空列表 [] 表示检测所有类别
  algorithm_classes:
    "火焰检测": ["fire", "smoke"]      # 只检测火和烟
    "人员检测": ["person"]              # 只检测人
    "垃圾分类": []                      # 检测所有垃圾类别
    "裸土检测": []                      # 检测所有类别
  
  # 是否在启动时预加载所有模型
  preload_all: true
```

### 🎯 类别过滤说明

**为什么需要类别过滤？**

同一个模型可能训练了多个类别，但实际应用中只需要检测部分类别：

- ✅ **人员检测**：模型可能包含"person"、"helmet"、"vest"，但我们只需要检测"person"
- ✅ **火焰检测**：只关注"fire"和"smoke"，忽略其他类别
- ✅ **垃圾分类**：需要检测所有垃圾类别，设置为空列表 `[]`

**配置示例**：

```yaml
# 示例1: 只检测人，忽略安全帽和反光衣
algorithm_classes:
  "人员检测": ["person"]

# 示例2: 检测火和烟
algorithm_classes:
  "火焰检测": ["fire", "smoke"]

# 示例3: 检测所有类别（不过滤）
algorithm_classes:
  "综合检测": []
```

### 添加新算法

只需在配置文件中添加一行：

```yaml
algorithm_models:
  "新算法名称": "模型文件路径"
```

## 📡 场景下发

### 请求格式

```json
{
  "scene": "随意填写或忽略",
  "algorithm": "火焰检测",  // 关键字段：算法名称
  "devices": [...],
  "startDate": "2024-11-08 10:00:00",
  "endDate": "2025-11-08 10:00:00"
}
```

### 工作流程

1. **接收请求** → 提取 `algorithm` 字段
2. **查找映射** → 从配置中获取模型路径
3. **加载模型** → 使用模型管理器加载（如未加载）
4. **启动检测** → 使用对应模型进行检测

### 示例

#### 示例1：火灾检测

```bash
curl -X POST http://localhost:8080/api/v1/scene/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "scene": "明火告警",
    "algorithm": "火焰检测",
    "devices": [{
      "deviceGbCode": "31011500001320000001",
      "area": "(100,100),(500,100),(500,400),(100,400)"
    }],
    "startDate": "2024-11-08 10:00:00",
    "endDate": "2025-11-08 10:00:00"
  }'
```

系统会：
- 读取算法：`火焰检测`
- 使用模型：`pt_dir/fire_smoke/best.pt`

#### 示例2：人员检测

```bash
curl -X POST http://localhost:8080/api/v1/scene/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "scene": "高温作业预警",
    "algorithm": "人员检测",
    "devices": [...]
  }'
```

系统会：
- 读取算法：`人员检测`
- 使用模型：`pt_dir/person/best.pt`

## 🔍 查询支持的算法

### API接口

```bash
GET /api/v1/algorithms
```

### 响应示例

```json
{
  "success": true,
  "data": {
    "algorithms": {
      "火焰检测": {
        "model_path": "pt_dir/fire_smoke/best.pt",
        "file_exists": true,
        "model_loaded": true,
        "target_classes": ["fire", "smoke"]
      },
      "人员检测": {
        "model_path": "pt_dir/person/best.pt",
        "file_exists": true,
        "model_loaded": true,
        "target_classes": ["person"]
      },
      "垃圾分类": {
        "model_path": "pt_dir/constuction_waste/constuction_waste/best.pt",
        "file_exists": true,
        "model_loaded": true,
        "target_classes": []
      },
      "裸土检测": {
        "model_path": "pt_dir/luotu/best.pt",
        "file_exists": true,
        "model_loaded": true,
        "target_classes": []
      }
    },
    "total": 4
  }
}
```

## ⏰ 场景生命周期管理

### 📅 时间字段说明

场景下发时需要提供 `startDate` 和 `endDate`：

```json
{
  "algorithm": "火焰检测",
  "startDate": "2024-11-08 10:00:00",  // 开始时间（记录用）
  "endDate": "2024-11-09 10:00:00"     // 结束时间（自动停止）
}
```

**字段用途**：
- 🔵 **`startDate`**：记录场景的计划开始时间（**不影响实际启动**）
  - 场景下发后会**立即启动检测**，不会等到 `startDate`
  - 此字段主要用于记录和查询
  
- 🔴 **`endDate`**：场景的结束时间（**会自动停止**）
  - 系统监控此时间，到期自动停止检测
  - 是实际生效的时间控制字段

### 🚀 启动机制

**立即启动策略**：

```
场景下发 → 立即获取流地址 → 立即启动检测 → 立即开始心跳
     ↓
不等待 startDate
```

**为什么这样设计？**
1. ✅ 符合实时监控需求（下发即启动）
2. ✅ 避免复杂的定时调度
3. ✅ 如需延迟，调用方可控制下发时间

### 🛑 停止机制

视频检测有**两种停止方式**：

#### 1. 自动停止（基于 endDate）

系统会监控 `endDate`，到期自动停止：

**工作原理**：
- ✅ 系统每 **30秒** 检查一次所有场景的结束时间
- ✅ 到达 `endDate` 后，自动停止该场景的所有检测任务
- ✅ 停止所有关联的视频流
- ✅ 停止心跳保活

**日志示例**：
```
INFO - 场景已到期: scene_xxx, 算法=火焰检测, 结束时间=2024-11-09 10:00:00
INFO - 已自动停止到期场景: scene_xxx
INFO - 停止场景成功: scene_xxx, 停止了3个设备
```

#### 2. 手动停止（API）

在 `endDate` 之前，可通过 API 手动停止：

```bash
POST /api/v1/scene/{scene_id}/stop
```

**示例**：
```bash
curl -X POST http://localhost:8080/api/v1/scene/scene_12345/stop
```

**响应**：
```json
{
  "status": 0,
  "message": "场景停止成功",
  "data": {
    "stopped_devices": 3
  }
}
```

### 📝 时间格式要求

`startDate` 和 `endDate` 必须使用格式：`YYYY-MM-DD HH:MM:SS`

**示例**：
- ✅ `"2024-11-08 10:00:00"`
- ✅ `"2025-12-31 23:59:59"`
- ❌ `"2024/11/08 10:00:00"` (格式错误)
- ❌ `"2024-11-08"` (缺少时间)

### 💡 使用建议

**场景1：长期监控**
```json
{
  "startDate": "2024-11-08 00:00:00",
  "endDate": "2025-12-31 23:59:59"  // 一年后到期
}
```

**场景2：短期任务**
```json
{
  "startDate": "2024-11-08 09:00:00",
  "endDate": "2024-11-08 18:00:00"  // 当天下班自动停止
}
```

**场景3：测试调试**
```json
{
  "startDate": "2024-11-08 10:00:00",
  "endDate": "2024-11-08 10:30:00"  // 30分钟后自动停止
}
```

## 🚀 启动流程

### 1. 系统启动时预加载

```
INFO - 预加载AI模型...
INFO - 正在加载模型: pt_dir/fire_smoke/best.pt
INFO - 模型加载成功: pt_dir/fire_smoke/best.pt
  - 类别数量: 2
  - 设备: cpu
INFO - 正在加载模型: pt_dir/person/best.pt
INFO - 模型加载成功: pt_dir/person/best.pt
  - 类别数量: 1
  - 设备: cpu
...
INFO - 模型预加载完成: 4/4 个模型可用
INFO -   ✓ 火焰检测: pt_dir/fire_smoke/best.pt
INFO -   ✓ 人员检测: pt_dir/person/best.pt
INFO -   ✓ 垃圾分类: pt_dir/constuction_waste/constuction_waste/best.pt
INFO -   ✓ 裸土检测: pt_dir/luotu/best.pt
```

### 2. 场景下发时使用

```
INFO - 收到场景下发请求: {"scene": "明火告警", "algorithm": "火焰检测", ...}
INFO - 算法 '火焰检测' -> 模型: pt_dir/fire_smoke/best.pt
INFO - 启动检测任务...
```

## 📝 配置模板

### 最小配置

```yaml
model:
  algorithm_models:
    "火焰检测": "pt_dir/fire_smoke/best.pt"
  preload_all: false  # 按需加载
```

### 完整配置

```yaml
model:
  # 默认模型
  default: "pt_dir/person/best.pt"
  
  # 算法映射
  algorithm_models:
    "火焰检测": "pt_dir/fire_smoke/best.pt"
    "烟雾检测": "pt_dir/fire_smoke/best.pt"  # 可复用同一模型
    "人员检测": "pt_dir/person/best.pt"
    "安全帽检测": "pt_dir/safety/helmet.pt"
    "反光衣检测": "pt_dir/safety/vest.pt"
    "垃圾分类": "pt_dir/constuction_waste/constuction_waste/best.pt"
    "裸土检测": "pt_dir/luotu/best.pt"
  
  # 算法类别过滤（可选）
  algorithm_classes:
    "火焰检测": ["fire", "smoke"]
    "人员检测": ["person"]
  
  # 预加载
  preload_all: true
```

## 💡 使用技巧

### 1. 多算法共用模型

```yaml
algorithm_models:
  "火焰检测": "pt_dir/fire_smoke/best.pt"
  "烟雾检测": "pt_dir/fire_smoke/best.pt"  # 同一个模型
```

### 2. 按需加载模式

```yaml
model:
  preload_all: false  # 不预加载
```

- 首次使用时自动加载
- 节省内存
- 适合算法很多但不常用的场景

### 3. 预加载模式（推荐）

```yaml
model:
  preload_all: true  # 启动时加载
```

- 启动稍慢，但后续无延迟
- 适合生产环境
- 场景切换立即响应

## ❓ 常见问题

### Q: 如何添加新算法？

A: 在配置文件中添加映射，无需修改代码：

```yaml
algorithm_models:
  "新算法": "path/to/new_model.pt"
```

### Q: 算法名称必须固定吗？

A: 不必须。算法名称由你在配置中定义，场景下发时使用相同名称即可。

### Q: 如果算法未配置会怎样？

A: 系统返回错误：

```json
{
  "status": 1,
  "message": "未找到算法 'xxx' 对应的模型"
}
```

### Q: 模型文件不存在怎么办？

A: 启动时会警告，场景下发时会失败。请确保模型文件路径正确。

### Q: 可以动态添加算法吗？

A: 修改配置文件后，重启服务即可生效。

## 🎯 优势

1. **简单** - 只关注算法名称，一行配置搞定
2. **灵活** - 随时添加新算法，无需改代码
3. **清晰** - 配置文件即文档，一目了然
4. **高效** - 模型预加载，场景切换无延迟
5. **复用** - 多个算法可以共用一个模型

---

**配置即用，简单高效！** 🎉


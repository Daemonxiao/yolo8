# Docker 镜像加速器配置指南（macOS）

## 🎯 为什么需要配置

在国内访问 Docker Hub 会非常慢或超时，配置镜像加速器后可以从国内节点下载镜像，速度提升 10-100 倍。

---

## 📱 macOS Docker Desktop 配置步骤

### 步骤1：打开 Docker Desktop

点击菜单栏的 Docker 图标，或使用命令：
```bash
open -a Docker
```

### 步骤2：进入设置

1. 点击 Docker Desktop 窗口右上角的 **齿轮图标 ⚙️**
2. 或点击菜单栏 Docker 图标 → **Settings / Preferences**

### 步骤3：选择 Docker Engine

在左侧菜单中选择 **"Docker Engine"**

### 步骤4：编辑配置

你会看到一个 JSON 配置编辑器，内容类似：

```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false
}
```

### 步骤5：添加镜像加速器配置

在 JSON 配置中添加 `"registry-mirrors"` 字段：

```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://mirror.ccs.tencentyun.com",
    "https://registry.docker-cn.com"
  ]
}
```

**⚠️ 注意：**
- 添加在最后，前面的字段后要有逗号
- 确保 JSON 格式正确（可以用在线 JSON 验证工具检查）

### 步骤6：应用并重启

1. 点击右下角 **"Apply & Restart"** 按钮
2. 等待 Docker 重启（通常需要 10-30 秒）
3. 看到 "Docker is running" 表示重启完成

---

## ✅ 验证配置

### 方法1：查看 Docker 信息

```bash
docker info | grep -A 5 "Registry Mirrors"
```

应该看到：
```
Registry Mirrors:
  https://docker.mirrors.ustc.edu.cn/
  https://mirror.ccs.tencentyun.com/
  https://registry.docker-cn.com/
```

### 方法2：测试拉取镜像

```bash
docker pull hello-world
```

如果能快速下载完成，说明配置成功！

---

## 🌟 推荐的国内镜像源

### 1. 中国科技大学镜像（推荐）
```
https://docker.mirrors.ustc.edu.cn
```
- 速度快，稳定性好
- 教育网和公网都可访问

### 2. 腾讯云镜像
```
https://mirror.ccs.tencentyun.com
```
- 大厂维护，稳定
- 适合腾讯云用户

### 3. Docker 官方中国镜像
```
https://registry.docker-cn.com
```
- Docker 官方提供
- 偶尔会有延迟

### 4. 阿里云镜像（需要注册）
```
https://<你的ID>.mirror.aliyuncs.com
```
- 需要在阿里云注册账号获取专属地址
- 速度快，稳定性高
- 注册地址：https://cr.console.aliyun.com/cn-hangzhou/instances/mirrors

### 5. 华为云镜像
```
https://05f073ad3c0010ea0f4bc00b7105ec20.mirror.swr.myhuaweicloud.com
```
- 适合华为云用户

---

## 🔍 常见问题

### Q1: 配置后还是很慢？

**解决方案：**
1. 检查配置是否正确（JSON 格式）
2. 确认 Docker 已重启
3. 尝试更换其他镜像源
4. 检查网络连接

### Q2: Apply & Restart 按钮是灰色的？

**原因：** JSON 格式错误

**解决方案：**
1. 检查是否有语法错误（逗号、引号、括号）
2. 使用 JSONLint 验证：https://jsonlint.com/
3. 复制本文档中的完整配置

### Q3: 重启后看不到镜像加速器？

**解决方案：**
```bash
# 查看完整的 Docker 配置
docker info

# 如果看不到 Registry Mirrors，可能配置未生效
# 尝试完全退出 Docker Desktop 后重新打开
```

### Q4: 某个镜像源失效了？

**解决方案：**
- 删除失效的镜像源
- 添加新的可用镜像源
- 镜像源会定期更新，建议关注官方公告

### Q5: 可以配置多个镜像源吗？

**可以！** Docker 会按顺序尝试：
```json
"registry-mirrors": [
  "https://docker.mirrors.ustc.edu.cn",    // 优先使用
  "https://mirror.ccs.tencentyun.com",     // 第二选择
  "https://registry.docker-cn.com"         // 备用
]
```

---

## 🚀 配置完成后的测试

### 1. 重新构建项目镜像

```bash
cd /Users/mx/PythonProject/yolo8/docker
docker-compose build
```

### 2. 观察下载速度

配置前：
```
[+] Building 300.0s (timeout after 5 minutes)
```

配置后：
```
[+] Building 15.2s (completed successfully)
```

---

## 📊 速度对比

| 镜像源 | 拉取 python:3.10-slim 耗时 |
|--------|---------------------------|
| Docker Hub (直连) | 5-10 分钟 或超时 |
| 中科大镜像 | 10-30 秒 ⭐ |
| 腾讯云镜像 | 15-40 秒 |
| 阿里云镜像 | 10-25 秒 ⭐ |

---

## 💡 其他优化建议

### 1. 使用国内 PyPI 镜像

在 `Dockerfile` 中已经配置：
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 使用国内 APT 镜像

在 `Dockerfile` 中已经配置：
```dockerfile
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list
```

### 3. 构建时使用缓存

```bash
# 使用构建缓存加速
docker-compose build --parallel

# 清理旧的构建缓存（如果遇到问题）
docker builder prune -a
```

---

## 🎉 配置成功标志

当你看到以下输出时，说明配置成功：

```bash
$ docker info | grep -A 5 "Registry Mirrors"
Registry Mirrors:
  https://docker.mirrors.ustc.edu.cn/
  https://mirror.ccs.tencentyun.com/
  https://registry.docker-cn.com/
```

```bash
$ docker pull python:3.10-slim
3.10-slim: Pulling from library/python
✓ 已完成 [==================================================>]
Status: Downloaded newer image for python:3.10-slim
```

---

**配置完成后，回到项目目录重新构建：**

```bash
cd /Users/mx/PythonProject/yolo8/docker
docker-compose build
```

现在速度应该会快很多！🚀


# pip install 完整指南

## 目录
- [基本概念](#基本概念)
- [安装方式对比](#安装方式对比)
- [安装流程详解](#安装流程详解)
- [常用命令](#常用命令)
- [最佳实践](#最佳实践)

---

## 基本概念

### Wheel 包 (.whl)

**Wheel** 是 Python 的标准二进制分发格式，本质上是一个 **ZIP 压缩包**。

**文件名格式：**
```
mcp_mysql-0.1.0-py3-none-any.whl
    ↓        ↓    ↓    ↓    ↓
  包名    版本  Python ABI  平台
                版本         
```

- `py3` - Python 3
- `none` - 不依赖特定 ABI
- `any` - 任何平台（Windows/Mac/Linux）

**Wheel 包内容：**
```
mcp_mysql-0.1.0-py3-none-any.whl (ZIP格式)
├── mcp_mysql/               ← 项目代码
│   ├── __init__.py
│   └── server.py
└── mcp_mysql-0.1.0.dist-info/  ← 元数据
    ├── METADATA             (项目信息、依赖)
    ├── WHEEL               (wheel 规范信息)
    ├── RECORD              (已安装文件列表)
    └── entry_points.txt    (命令行入口点)
```

### 类比其他语言

| 语言 | 包格式 |
|------|--------|
| Java | `.jar` |
| Node.js | `.tgz` |
| Python | `.whl` |

---

## 安装方式对比

### 1. 从 PyPI 安装

```bash
pip install colorama
```

**流程：**
```
查找包 → 下载 wheel → 缓存 → 解压到 site-packages
```

**结果：**
```
.venv/Lib/site-packages/
├── colorama/                    ← 解压的代码
└── colorama-0.4.6.dist-info/    ← 解压的元数据
```

### 2. 本地普通安装

```bash
pip install .
```

**流程：**
```
读取 pyproject.toml → 构建临时 wheel → 解压安装 → 删除临时 wheel
```

**特点：**
- ✅ 代码被**复制**到 site-packages
- ❌ 修改源码不会生效，需要重新安装

**结果：**
```
.venv/Lib/site-packages/
├── mcp_mysql/                   ← 复制的代码
└── mcp_mysql-0.1.0.dist-info/   ← 元数据
```

### 3. Editable 安装（开发模式）

```bash
pip install -e .
```

**流程：**
```
读取 pyproject.toml → 只构建元数据 → 创建链接到源码
```

**特点：**
- ✅ 修改源码**立即生效**
- ✅ 适合开发调试
- ✅ 代码不复制，节省空间

**结果：**
```
.venv/Lib/site-packages/
└── mcp_mysql-0.1.0.dist-info/
    ├── METADATA
    ├── RECORD
    └── direct_url.json          ← 指向源码目录的链接
    
源码位置：D:/Projects/mcp_mysql/mcp_mysql/  (原地不动)
```

### 对比表格

| 方式 | 命令 | 构建 Wheel | 代码位置 | 修改生效 | 使用场景 |
|------|------|-----------|---------|---------|----------|
| PyPI | `pip install pkg` | 下载现成的 | site-packages | - | 安装第三方包 |
| 普通 | `pip install .` | 临时构建 | site-packages | ❌ 需重装 | 生产部署 |
| Editable | `pip install -e .` | 只构建元数据 | 源码目录 | ✅ 立即生效 | 开发调试 |

---

## 安装流程详解

### 完整安装流程（pip install colorama）

```
1️⃣ 查找包
   pip 连接 PyPI (https://pypi.org)
   搜索 colorama 的最新版本
   ↓
   
2️⃣ 下载 Wheel
   colorama-0.4.6-py2.py3-none-any.whl
   ↓
   
3️⃣ 保存到缓存
   Windows: %LOCALAPPDATA%/pip/cache/
   Linux/Mac: ~/.cache/pip/
   ↓
   
4️⃣ 解压 Wheel 到 site-packages
   .venv/Lib/site-packages/
   ├── colorama/           ← 代码
   └── colorama-0.4.6.dist-info/  ← 元数据
   ↓
   
5️⃣ 注册到已安装列表
   记录到 pip 的数据库
   ✓ 安装完成
```

### Wheel 文件的生命周期

```
[构建/下载阶段]
colorama-0.4.6-py2.py3-none-any.whl  ← Wheel 文件
   ↓
   
[缓存阶段]
~/.cache/pip/wheels/...              ← 保存以备重用
   ↓
   
[安装阶段]
解压到 site-packages
├── colorama/                        ← 代码
└── colorama-0.4.6.dist-info/
    └── WHEEL                        ← 记录来自哪个 wheel
   ↓
   
[完成]
Wheel 文件保留在缓存中
下次安装相同版本时直接使用缓存（快！）
```

### 依赖解析流程

当你运行 `pip install mcp-mysql` 时：

```
1️⃣ 读取 pyproject.toml
   dependencies = [
       "mcp>=0.9.0",
       "mysql-connector-python>=8.0.0",
       "starlette>=0.27.0",
       "uvicorn>=0.23.0",
       "sse-starlette>=1.6.0",
   ]
   ↓
   
2️⃣ 递归解析依赖
   mcp 依赖 → httpx, pydantic
   pydantic 依赖 → typing-extensions, annotated-types
   starlette 依赖 → anyio
   anyio 依赖 → idna, sniffio
   ...
   ↓
   
3️⃣ 解析完成
   Resolved 34 packages  ← 你的包 + 直接依赖 + 间接依赖
   ↓
   
4️⃣ 按顺序安装
   先安装底层依赖，再安装上层依赖
```

---

## 常用命令

### 安装相关

```bash
# 从 PyPI 安装
pip install package_name

# 安装指定版本
pip install package_name==1.2.3

# 安装最小版本要求
pip install "package_name>=1.2.0"

# 从本地目录安装
pip install .

# Editable 安装（开发模式）
pip install -e .

# 从 requirements.txt 安装
pip install -r requirements.txt

# 升级包
pip install --upgrade package_name
```

### 查询相关

```bash
# 列出所有已安装的包
pip list

# 查看包详情
pip show package_name

# 查看包依赖树（需要先安装 pipdeptree）
pip install pipdeptree
pipdeptree -p package_name

# 列出过时的包
pip list --outdated
```

### 卸载相关

```bash
# 卸载包
pip uninstall package_name

# 自动确认卸载
pip uninstall package_name -y

# 卸载多个包
pip uninstall pkg1 pkg2 pkg3 -y
```

### 构建相关

```bash
# 构建 wheel 包（需要安装 build）
pip install build
python -m build

# 生成的文件：
# dist/package_name-0.1.0-py3-none-any.whl

# 只构建 wheel，不安装
pip wheel . --no-deps
```

### 导出依赖

```bash
# 导出当前环境的所有包（包含版本号）
pip freeze > requirements.txt

# 导出项目的直接依赖（推荐）
# 手动编辑 requirements.txt 或使用 pip-tools
```

---

## 最佳实践

### 1. 使用虚拟环境

**为什么？**
- ✅ 隔离项目依赖
- ✅ 避免版本冲突
- ✅ 便于清理和重建

**创建和使用：**
```bash
# 使用 venv（标准库）
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 使用 uv（推荐，更快）
uv venv
.venv\Scripts\activate
```

### 2. 使用 python -m pip

**为什么？**
```bash
# ❌ 不推荐：可能调用错误的 pip
pip install package

# ✅ 推荐：确保使用当前 Python 的 pip
python -m pip install package
```

**好处：**
- 保证 pip 和 python 在同一环境
- 避免 PATH 环境变量问题
- 虚拟环境更可靠

### 3. 开发时使用 -e 模式

```bash
# 开发阶段
pip install -e .

# 好处：
# - 修改代码立即生效
# - 无需重复安装
# - 节省时间
```

### 4. 使用 uv 加速安装

```bash
# 安装 uv
pip install uv

# 使用 uv 安装（速度快 10-100 倍）
uv pip install package_name
uv pip install -e .
```

### 5. 固定依赖版本

**开发环境：**
```toml
# pyproject.toml - 使用范围版本
dependencies = [
    "mcp>=0.9.0",              # 允许小版本更新
    "starlette>=0.27.0",
]
```

**生产环境：**
```txt
# requirements.txt - 锁定精确版本
mcp==0.9.0
starlette==0.27.5
```

生成锁定版本：
```bash
pip freeze > requirements.txt
```

### 6. 检查依赖安全

```bash
# 检查已知漏洞（需要安装 pip-audit）
pip install pip-audit
pip-audit
```

### 7. 清理缓存

```bash
# 查看缓存位置
pip cache dir

# 清理所有缓存
pip cache purge

# 查看缓存大小
pip cache info
```

---

## 常见问题

### Q: pip 和 python -m pip 有什么区别？

**A:** `python -m pip` 确保使用当前 Python 解释器对应的 pip，避免环境混乱。

```bash
# 可能调用全局 pip
pip install xxx

# 确保调用虚拟环境的 pip
python -m pip install xxx
```

### Q: -e 安装后修改代码为什么立即生效？

**A:** 因为 `-e` 模式创建的是**链接**，不是复制：

```
site-packages/package.pth  →  指向源码目录
Python 导入时 →  直接读取源码目录
修改源码 →  立即生效
```

### Q: wheel 文件安装后去哪了？

**A:** Wheel 文件被解压到 `site-packages`，原始 `.whl` 文件保存在缓存中：

```
缓存位置（保留 wheel）：
~/.cache/pip/wheels/

安装位置（解压后）：
.venv/Lib/site-packages/
```

### Q: 如何查看某个包依赖哪些其他包？

```bash
# 方法1：使用 pip show
pip show package_name

# 方法2：使用 pipdeptree
pip install pipdeptree
pipdeptree -p package_name
```

### Q: 为什么 uv 警告 hardlink 失败？

**A:** 当缓存和项目在不同磁盘时，无法创建硬链接，uv 会退回到复制模式。

```bash
# 不影响功能，只是稍微慢一点
# 如果想消除警告：
export UV_LINK_MODE=copy  # Linux/Mac
$env:UV_LINK_MODE="copy"  # Windows
```

---

## 总结

### 核心概念

1. **Wheel = Python 的安装包格式**（ZIP 压缩包）
2. **pip install 流程** = 下载/构建 → 缓存 → 解压 → 注册
3. **-e 模式** = 链接源码，适合开发
4. **普通模式** = 复制代码，适合部署

### 推荐工作流

```bash
# 1. 创建虚拟环境
uv venv

# 2. 激活虚拟环境
.venv\Scripts\activate

# 3. 开发模式安装
python -m pip install -e .

# 4. 开发调试...

# 5. 构建分发包
python -m build

# 6. 生产部署
pip install dist/package-0.1.0-py3-none-any.whl
```

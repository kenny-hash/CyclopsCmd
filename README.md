# CyclopsCmd

CyclopsCmd 是一个面向批量服务器运维的 Web 控制台。前端使用 React + Vite + Handsontable 提供表格式服务器与命令录入界面，后端使用 FastAPI + AsyncSSH 执行 SSH 命令，并通过 WebSocket 实时回传执行进度和结果。

## 功能概览

- **表格式批量执行**：在前端表格中维护服务器 IP、登录用户、端口、密码和待执行命令。
- **实时输出**：提交命令后，后端通过 WebSocket 向浏览器推送每台服务器的执行状态、标准输出和错误信息。
- **跳板机支持**：可按行配置跳板机信息，用于访问内网服务器。
- **配置保存**：后端使用 SQLite 保存服务器配置，便于复用常用执行模板。
- **前后端分离**：Vite 开发服务器代理 `/api` 请求到 FastAPI，后端固定提供 REST API 与 WebSocket 服务。

## 当前目录结构

```text
CyclopsCmd/
├── README.md                    # 项目说明、目录结构和启动方式
├── index.html                   # Vite 前端入口 HTML
├── package.json                 # 前端依赖与 npm 脚本
├── pyproject.toml               # 后端 Python 包构建配置
├── vite.config.js               # Vite 配置；开发环境代理 /api 到后端
├── vitest.config.ts             # Vitest 前端测试配置
├── backend/
│   ├── app.py                   # FastAPI 主应用；REST API、WebSocket、SSH 执行与 SQLite 模型
│   ├── App.py                   # 旧版/备用后端实现，保留用于兼容
│   ├── requirements.txt         # 后端运行、测试与构建依赖
│   └── tests/
│       └── test_smoke.py        # 后端基础冒烟测试
├── public/
│   └── logo.svg                 # 静态 Logo 资源
├── scripts/
│   ├── build_backend.sh         # 后端 Python 包构建脚本
│   ├── start.sh                 # 一键启动前端与后端的开发脚本
│   └── test_backend.sh          # 后端测试脚本
├── desktop/
│   └── electron/                # 独立 Electron 桌面壳与打包配置，不影响原 Web 模式
└── src/
    ├── App.jsx                  # 前端主页面与批量执行交互逻辑
    ├── App.css                  # 主页面样式
    ├── ShadcnModals.jsx         # 弹窗相关 UI
    ├── ansi-to-html.js          # ANSI 终端输出转 HTML 工具
    ├── main.jsx                 # React 挂载入口
    ├── shadcnComponents.js      # shadcn 风格组件导出/封装
    ├── tailwind.config.js       # Tailwind/shadcn 相关配置
    ├── components/ui/           # 通用 UI 组件
    └── lib/utils.js             # 前端通用工具函数
```

> 运行后后端会在项目根目录生成 `test.db` SQLite 数据库文件；该文件属于本地运行数据，不需要提交到代码仓库。

## 环境要求

- Node.js 18+（建议使用当前 LTS 版本）
- npm 9+
- Python 3.8+
- 可访问目标服务器的网络环境与 SSH 凭据

## 快速启动

推荐使用仓库内的一键启动脚本：

```bash
./scripts/start.sh
```

脚本会执行以下操作：

1. 在项目根目录创建或复用 `.venv` Python 虚拟环境。
2. 安装 `backend/requirements.txt` 中的后端依赖。
3. 若不存在 `node_modules`，执行 `npm install` 安装前端依赖。
4. 启动 FastAPI 后端：`http://127.0.0.1:8000`。
5. 启动 Vite 前端：`http://127.0.0.1:5173`。
6. 在退出时自动清理前端和后端子进程。

启动完成后，在浏览器打开：

```text
http://127.0.0.1:5173
```

### 启动脚本常用环境变量

```bash
# 跳过依赖安装，仅启动服务
SKIP_INSTALL=1 ./scripts/start.sh

# 自定义端口
BACKEND_PORT=9000 FRONTEND_PORT=5174 ./scripts/start.sh

# 自定义监听地址
BACKEND_HOST=0.0.0.0 FRONTEND_HOST=0.0.0.0 ./scripts/start.sh

# 使用已有虚拟环境目录
VENV_DIR=.venv-dev ./scripts/start.sh
```

前端开发服务器会把 `/api/*` 请求代理到 `VITE_BACKEND_TARGET`，默认值为 `http://127.0.0.1:8000`。WebSocket 连接默认使用 `VITE_BACKEND_WS_HOST` 和 `VITE_BACKEND_WS_PORT`，一键启动脚本会根据后端启动参数自动设置。

如需连接远端后端：

```bash
VITE_BACKEND_TARGET=http://192.168.1.10:8000 VITE_BACKEND_WS_HOST=192.168.1.10 VITE_BACKEND_WS_PORT=8000 ./scripts/start.sh
```

## 手动启动方式

如果不使用一键脚本，也可以分两个终端手动启动。

### 1. 启动后端

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8000
```

### 2. 启动前端

```bash
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

然后访问 `http://127.0.0.1:5173`。

## 常用开发命令

```bash
# 前端开发服务
npm run dev

# 前端生产构建
npm run build

# 前端测试
npm test -- --run

# 后端测试
./scripts/test_backend.sh

# 后端包构建
./scripts/build_backend.sh

# Electron 桌面壳开发与打包
cd desktop/electron
npm install
npm run dev
npm run build
```


## Electron 桌面打包

仓库新增 `desktop/electron/` 作为独立桌面壳工程，用于把现有 React 前端和 FastAPI 后端打包为可分发 App；原有 Web 开发、静态部署和前后端分离运行方式不变。

桌面壳会在启动时选择空闲本地端口，拉起本地 FastAPI 后端，并通过 preload 将 API 与 WebSocket 地址注入前端。后端 SQLite 数据会保存到 Electron 用户数据目录下，避免继续使用仓库根目录的 `test.db`。

更多开发、构建和分发说明见 `desktop/electron/README.md`。

## API 与运行说明

- `POST /api/v1/execute`：提交待执行的服务器与命令列表，后端返回 WebSocket 房间号。
- `GET /api/v1/configs`：读取已保存配置列表。
- `POST /api/v1/configs`：保存配置。
- `GET /api/v1/configs/{config_id}`：读取指定配置详情。
- `DELETE /api/v1/configs/{config_id}`：删除指定配置。
- `WS /ws/{room}`：实时接收命令执行输出和完成状态。

前端 WebSocket 默认连接 `VITE_BACKEND_WS_HOST:VITE_BACKEND_WS_PORT`；未设置时使用当前页面主机和 `8000` 端口。

## 安全提示

- 当前后端 CORS 策略允许所有来源，生产部署前应限制为可信域名。
- 不建议在代码、README 或配置模板中保存真实服务器密码。
- 跳板机与目标服务器凭据应通过安全的运行时输入、密钥管理或加密配置管理方案维护。
- 批量执行命令具备较高风险，请先在测试服务器验证命令效果。

## GitHub Actions 自动测试与部署到 Pages

本项目已提供 `.github/workflows/pages.yml`，用于在 GitHub Actions 中自动完成前端测试、后端测试、前端构建，并把构建产物发布到 GitHub Pages。

### 工作流会做什么

- 在 `push` 到 `main`、创建/更新 Pull Request、或手动触发 `workflow_dispatch` 时运行。
- 使用 Node.js 20 执行 `npm ci`、`npm test -- --run` 和 `npm run build`。
- 使用 Python 3.11 安装 `backend/requirements.txt` 并执行 `./scripts/test_backend.sh`。
- Pull Request 只测试和构建，不部署。
- 非 Pull Request 事件（例如推送到 `main` 或手动触发）会把 `dist/` 部署到 GitHub Pages。

> 注意：GitHub Pages 只能托管静态前端资源，不能运行 FastAPI 后端。部署后的页面若要调用接口，需要将后端单独部署到可公网访问的平台，并在构建时按需设置 `VITE_BACKEND_API_BASE_URL` 和 `VITE_BACKEND_WS_URL`。

### 首次启用步骤

1. 将代码推送到 GitHub 仓库，并确保默认分支或部署分支名为 `main`；如果你的默认分支是 `master`，请把 `.github/workflows/pages.yml` 里的 `branches: [main]` 改为 `master`。
2. 打开 GitHub 仓库页面，进入 **Settings → Pages**。
3. 在 **Build and deployment** 中将 **Source** 选择为 **GitHub Actions**。
4. 推送一次到 `main`，或进入 **Actions → Test and deploy to GitHub Pages → Run workflow** 手动运行。
5. 工作流成功后，在 **Settings → Pages** 或 Actions 部署日志中查看访问地址，通常是 `https://<用户名或组织名>.github.io/<仓库名>/`。

### 路径配置说明

Vite 默认按站点根路径构建。GitHub Pages 的项目站点通常部署在 `/<仓库名>/` 子路径下，因此工作流在构建时设置：

```yaml
env:
  VITE_BASE_PATH: /${{ github.event.repository.name }}/
```

`vite.config.js` 会读取 `VITE_BASE_PATH`，本地开发未设置该变量时仍使用 `/`，所以不影响 `npm run dev`。

如果你使用自定义域名并将站点部署到域名根路径，可以把工作流中的 `VITE_BASE_PATH` 改为 `/`。

### 连接单独部署的后端

如果前端部署在 GitHub Pages，而 FastAPI 后端部署在其他平台（例如云服务器、容器平台或 Serverless 平台），建议在 GitHub 仓库的 **Settings → Secrets and variables → Actions → Variables** 中添加：

- `VITE_BACKEND_API_BASE_URL`：后端 HTTP(S) 地址，例如 `https://api.example.com`。前端会请求 `${VITE_BACKEND_API_BASE_URL}/api/v1/...`。
- `VITE_BACKEND_WS_URL`：后端 WebSocket 地址，例如 `wss://api.example.com`。前端会连接 `${VITE_BACKEND_WS_URL}/ws/<room>`。

如果不设置这两个变量，前端会继续使用相对路径 `/api/v1/...`，WebSocket 会默认连接当前页面域名的 `8000` 端口，适合本地开发但通常不适合 GitHub Pages。

## GitHub Actions 构建 Electron App 与发布 Release

本项目还提供 `.github/workflows/electron-release.yml`，用于在 GitHub Actions 中自动完成测试、Web 前端构建、后端 sidecar 打包，以及 Windows、macOS、Linux 三个平台的 Electron 安装包构建。

### 工作流触发方式

- `pull_request`：运行测试并验证 Electron App 能否成功构建，产物只保留为 Actions artifact。
- `push` 到 `main`：运行测试和构建，产物可在对应 Actions run 的 **Artifacts** 区域下载，便于本地临时测试。
- 推送 `v*` 标签（例如 `v0.1.0`）：运行测试和构建，并把安装包上传到 GitHub Release 页面。
- `workflow_dispatch`：支持在 GitHub Actions 页面手动触发一次完整测试和构建。

### 本地与 CI 使用的测试命令

```bash
# 前端单元测试（Vitest）
npm test -- --run

# 前端生产构建
npm run build

# 后端 API/冒烟测试（pytest）
./scripts/test_backend.sh

# Electron 桌面 App 打包
cd desktop/electron
npm ci
npm run build
```

### 在 GitHub Release 页面提供可下载 App

GitHub 当前功能可以完成这个需求：当你推送形如 `v0.1.0` 的 Git tag 后，`electron-release.yml` 会在 GitHub Release 中创建/更新对应 Release，并上传各平台构建产物。示例：

```bash
git tag v0.1.0
git push origin v0.1.0
```

构建完成后，进入仓库的 **Releases** 页面即可下载 Windows、macOS、Linux 对应的安装包或压缩包。

> 注意：当前工作流禁用了 macOS 代码签名自动发现（`CSC_IDENTITY_AUTO_DISCOVERY=false`），因此生成的 macOS App 适合本地测试；如果要正式分发，建议后续接入 Apple Developer 证书、公证流程，以及 Windows 代码签名证书。

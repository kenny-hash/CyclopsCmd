# CyclopsCmd Electron 桌面壳

这个目录是独立的 Electron 桌面打包工程，用于把现有 React 前端和 FastAPI 后端组合成可分发的桌面 App。原有 Web 开发和部署方式仍然保留在仓库根目录。

## 目录说明

```text
desktop/electron/
├── main.cjs                         # Electron 主进程：启动后端、创建窗口、加载前端
├── preload.cjs                      # 向前端注入本地后端 API / WebSocket 地址
├── package.json                     # Electron 独立依赖、构建脚本和 electron-builder 配置
├── pyinstaller/backend_entry.py     # PyInstaller 后端入口，打包后启动 FastAPI
├── resources/backend-sidecar/       # 后端 sidecar 构建输出目录，不提交二进制产物
├── scripts/build-frontend.cjs        # 使用相对 base 路径构建 Electron 前端资源
└── scripts/build-backend-sidecar.cjs # 使用 PyInstaller 构建后端 sidecar
```

## 开发运行

先在仓库根目录准备前端构建产物，并确保当前 Python 环境或仓库 `.venv` 已安装后端依赖：

```bash
npm install
npm run build
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

然后进入 Electron 目录安装桌面端依赖并启动：

```bash
cd desktop/electron
npm install
npm run dev
```

开发模式默认会：

1. 选择一个空闲本地端口。
2. 用仓库根目录 `.venv` 里的 Python 启动 `uvicorn app:app --app-dir backend`。
3. 把 SQLite 数据放到 Electron 用户数据目录下的 `backend-data/`，避免污染仓库根目录。
4. 加载仓库根目录的 `dist/index.html`。

如果想让 Electron 连接 Vite 开发服务器，可以先在仓库根目录启动：

```bash
npm run dev
```

再用环境变量启动 Electron：

```bash
cd desktop/electron
ELECTRON_DEV_SERVER_URL=http://127.0.0.1:5173 npm run dev
```

## 构建可分发 App

```bash
cd desktop/electron
npm install
npm run build
```

`npm run build` 会依次执行：

1. `npm run build:frontend`：调用仓库根目录的 `npm run build -- --base=./` 生成适合 Electron 本地文件加载的 `dist/`。
2. `npm run build:backend`：使用 PyInstaller 把 FastAPI 后端打包为 `resources/backend-sidecar/cyclopscmd-backend`。
3. `electron-builder`：生成 Windows 或 macOS 桌面安装包。

构建产物默认输出到：

```text
desktop/electron/release/
```

## 分发注意事项

- Windows 分发建议配置代码签名证书，否则可能触发 SmartScreen 风险提示。
- macOS 分发建议配置 Developer ID 签名和 notarization，否则 Gatekeeper 可能阻止打开。
- 当前 Electron 壳只监听 `127.0.0.1` 本地后端地址；前端通过 preload 注入的地址访问 API 和 WebSocket。
- 后端 SQLite 数据位于 Electron 的用户数据目录，不再使用仓库根目录的 `test.db`。
- `resources/backend-sidecar/` 是构建输出目录，二进制产物不应提交到 Git。

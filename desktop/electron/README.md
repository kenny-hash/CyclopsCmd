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


## Windows 空白窗口调试

如果安装后打开 App 只有空白窗口，优先按下面顺序定位：

1. **确认前端资源是否正确加载**：Electron 使用 `file://` 加载生产构建产物，构建时必须使用相对资源路径。本工程的 `npm run build:frontend` 已通过 `scripts/build-frontend.cjs` 自动执行 `vite build --base=./`，请不要直接把面向 GitHub Pages 的前端产物拷进安装包。
2. **用开发者工具启动已安装 App**：在 PowerShell 中设置调试环境变量后再启动安装目录里的程序，窗口会自动打开 DevTools：

   ```powershell
   $env:CYCLOPSCMD_DEBUG = "1"
   & "$env:LOCALAPPDATA\Programs\CyclopsCmd\CyclopsCmd.exe"
   ```

   如果使用 zip 免安装包，请把命令里的 exe 路径替换为解压后的 `CyclopsCmd.exe`。
3. **查看主进程日志**：App 会把后端启动日志、前端控制台消息、页面加载失败和渲染进程崩溃信息写入用户数据目录：

   ```powershell
   Get-Content "$env:APPDATA\CyclopsCmd\logs\main.log" -Tail 200
   ```

4. **确认后端 sidecar 是否存在并可启动**：安装包内应包含 `resources/backend-sidecar/cyclopscmd-backend.exe`。如果日志里出现 `Backend sidecar not found`、端口等待超时或 Python/依赖错误，先在构建机器上重新执行 `cd desktop/electron; npm run build:backend`。
5. **在打包前本地复现**：优先运行 `npm run pack` 生成未安装目录版产物，再从 `desktop/electron/release/*-unpacked/` 直接启动 exe。这样可以快速验证资源、preload 注入和后端启动，而不用每次安装 NSIS 包。

常见原因是前端产物使用了 `/assets/...` 这类绝对路径；在 `file://` 场景下它会指向磁盘根目录，导致 JS/CSS 没加载，最终显示空白窗口。

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

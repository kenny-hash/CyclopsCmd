const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');

const BACKEND_HOST = '127.0.0.1';
const BACKEND_START_TIMEOUT_MS = 30000;

let backendProcess = null;
let backendPort = null;
let mainWindow = null;
let logFilePath = null;

function ensureLogFile() {
  if (logFilePath) {
    return logFilePath;
  }

  const logsDir = path.join(app.getPath('userData'), 'logs');
  fs.mkdirSync(logsDir, { recursive: true });
  logFilePath = path.join(logsDir, 'main.log');
  return logFilePath;
}

function appendLog(level, message) {
  const line = `[${new Date().toISOString()}] [${level}] ${message}\n`;
  if (app.isReady()) {
    fs.appendFileSync(ensureLogFile(), line);
  }

  const writer = level === 'ERROR' ? console.error : console.log;
  writer(line.trimEnd());
}

function isDebugEnabled() {
  return !app.isPackaged || process.env.CYCLOPSCMD_DEBUG === '1';
}

function defaultLogExportPath() {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  return path.join(app.getPath('downloads'), `cyclopscmd-debug-logs-${stamp}.log`);
}

async function exportDebugLogs() {
  const sourcePath = ensureLogFile();
  appendLog('INFO', 'Debug log export requested');

  const { canceled, filePath } = await dialog.showSaveDialog({
    title: 'Export CyclopsCmd Debug Logs',
    defaultPath: defaultLogExportPath(),
    buttonLabel: 'Export Logs',
    filters: [
      { name: 'Log Files', extensions: ['log'] },
      { name: 'Text Files', extensions: ['txt'] },
      { name: 'All Files', extensions: ['*'] },
    ],
  });

  if (canceled || !filePath) {
    appendLog('INFO', 'Debug log export canceled');
    return { canceled: true };
  }

  await fs.promises.copyFile(sourcePath, filePath);
  appendLog('INFO', `Debug logs exported to ${filePath}`);
  return { canceled: false, filePath };
}

function projectRoot() {
  return path.resolve(__dirname, '..', '..');
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, BACKEND_HOST, () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

function waitForPort(port, timeoutMs) {
  const startedAt = Date.now();

  return new Promise((resolve, reject) => {
    const tryConnect = () => {
      const socket = net.createConnection({ host: BACKEND_HOST, port });
      socket.once('connect', () => {
        socket.end();
        resolve();
      });
      socket.once('error', () => {
        socket.destroy();
        if (Date.now() - startedAt >= timeoutMs) {
          reject(new Error(`Backend did not start within ${timeoutMs}ms on ${BACKEND_HOST}:${port}`));
          return;
        }
        setTimeout(tryConnect, 250);
      });
    };

    tryConnect();
  });
}

function resolvePythonCommand() {
  if (process.env.ELECTRON_PYTHON) {
    return process.env.ELECTRON_PYTHON;
  }

  const root = projectRoot();
  const venvPython = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');

  if (fs.existsSync(venvPython)) {
    return venvPython;
  }

  return process.platform === 'win32' ? 'python' : 'python3';
}

function packagedBackendPath() {
  const executable = process.platform === 'win32' ? 'cyclopscmd-backend.exe' : 'cyclopscmd-backend';
  return path.join(process.resourcesPath, 'backend-sidecar', executable);
}

function backendSpawnConfig(port, dataDir) {
  if (app.isPackaged) {
    return {
      command: packagedBackendPath(),
      args: ['--host', BACKEND_HOST, '--port', String(port), '--data-dir', dataDir],
      options: { cwd: dataDir },
    };
  }

  return {
    command: resolvePythonCommand(),
    args: [
      '-m', 'uvicorn',
      'app:app',
      '--app-dir', path.join(projectRoot(), 'backend'),
      '--host', BACKEND_HOST,
      '--port', String(port),
    ],
    options: { cwd: dataDir },
  };
}

async function startBackend() {
  backendPort = await getFreePort();
  const dataDir = path.join(app.getPath('userData'), 'backend-data');
  fs.mkdirSync(dataDir, { recursive: true });

  const { command, args, options } = backendSpawnConfig(backendPort, dataDir);

  if (app.isPackaged && !fs.existsSync(command)) {
    throw new Error(`Backend sidecar not found: ${command}`);
  }

  backendProcess = spawn(command, args, {
    ...options,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  backendProcess.stdout.on('data', (data) => {
    appendLog('INFO', `[backend] ${data.toString().trimEnd()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    appendLog('ERROR', `[backend] ${data.toString().trimEnd()}`);
  });

  backendProcess.once('error', (error) => {
    appendLog('ERROR', `[backend] failed to start: ${error.message}`);
  });

  backendProcess.once('exit', (code, signal) => {
    appendLog('INFO', `[backend] exited code=${code} signal=${signal}`);
    backendProcess = null;
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('cyclopscmd-backend-exit', { code, signal });
    }
  });

  await waitForPort(backendPort, BACKEND_START_TIMEOUT_MS);
}

function frontendUrl() {
  if (!app.isPackaged && process.env.ELECTRON_DEV_SERVER_URL) {
    return process.env.ELECTRON_DEV_SERVER_URL;
  }

  const indexPath = app.isPackaged
    ? path.join(process.resourcesPath, 'frontend', 'index.html')
    : path.join(projectRoot(), 'dist', 'index.html');

  return `file://${indexPath}`;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 1024,
    minHeight: 700,
    title: 'CyclopsCmd',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments: [
        `--cyclopscmd-backend-host=${BACKEND_HOST}`,
        `--cyclopscmd-backend-port=${backendPort}`,
      ],
    },
  });

  mainWindow.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    appendLog('INFO', `[renderer:${level}] ${message} (${sourceId}:${line})`);
  });

  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    appendLog('ERROR', `[renderer] failed to load ${validatedURL}: ${errorCode} ${errorDescription}`);
  });

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    appendLog('ERROR', `[renderer] process gone: ${details.reason} exitCode=${details.exitCode}`);
  });

  const url = frontendUrl();
  appendLog('INFO', `Loading frontend: ${url}`);
  await mainWindow.loadURL(url);

  if (isDebugEnabled()) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
}

function stopBackend() {
  if (!backendProcess) {
    return;
  }

  const child = backendProcess;
  backendProcess = null;

  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
    return;
  }

  child.kill('SIGTERM');
}

ipcMain.handle('cyclopscmd-export-debug-logs', async () => exportDebugLogs());

app.whenReady()
  .then(startBackend)
  .then(createWindow)
  .catch((error) => {
    appendLog('ERROR', error.stack || error.message || String(error));
    dialog.showErrorBox('CyclopsCmd 启动失败', error.message || String(error));
    app.quit();
  });

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow().catch((error) => {
      appendLog('ERROR', error.stack || error.message || String(error));
      dialog.showErrorBox('CyclopsCmd 窗口启动失败', error.message || String(error));
    });
  }
});

app.on('before-quit', stopBackend);
app.on('quit', stopBackend);

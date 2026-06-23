const { contextBridge, ipcRenderer } = require('electron');

function readArg(name) {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : '';
}

const backendPort = readArg('cyclopscmd-backend-port');
const backendHost = readArg('cyclopscmd-backend-host') || '127.0.0.1';

contextBridge.exposeInMainWorld('__CYCLOPS_DESKTOP_CONFIG__', {
  apiBaseUrl: backendPort ? `http://${backendHost}:${backendPort}` : '',
  wsBaseUrl: backendPort ? `ws://${backendHost}:${backendPort}` : '',
  exportDebugLogs: () => ipcRenderer.invoke('cyclopscmd-export-debug-logs'),
});

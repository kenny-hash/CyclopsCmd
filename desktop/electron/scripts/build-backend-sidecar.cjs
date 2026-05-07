const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const electronDir = path.resolve(__dirname, '..');
const rootDir = path.resolve(electronDir, '..', '..');
const buildDir = path.join(electronDir, '.backend-build');
const venvDir = path.join(buildDir, 'venv');
const distDir = path.join(electronDir, 'resources', 'backend-sidecar');
const specDir = path.join(buildDir, 'spec');
const workDir = path.join(buildDir, 'work');
const entryFile = path.join(electronDir, 'pyinstaller', 'backend_entry.py');

const isWindows = process.platform === 'win32';
const python = process.env.PYTHON || (isWindows ? 'python' : 'python3');
const venvPython = isWindows
  ? path.join(venvDir, 'Scripts', 'python.exe')
  : path.join(venvDir, 'bin', 'python');
const pyinstaller = isWindows
  ? path.join(venvDir, 'Scripts', 'pyinstaller.exe')
  : path.join(venvDir, 'bin', 'pyinstaller');

function run(command, args, options = {}) {
  console.log(`> ${command} ${args.join(' ')}`);
  execFileSync(command, args, { stdio: 'inherit', ...options });
}

fs.rmSync(distDir, { recursive: true, force: true });
fs.rmSync(specDir, { recursive: true, force: true });
fs.rmSync(workDir, { recursive: true, force: true });
fs.mkdirSync(distDir, { recursive: true });
fs.mkdirSync(specDir, { recursive: true });
fs.mkdirSync(workDir, { recursive: true });

if (!fs.existsSync(venvPython)) {
  fs.mkdirSync(buildDir, { recursive: true });
  run(python, ['-m', 'venv', venvDir]);
}

run(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip']);
run(venvPython, ['-m', 'pip', 'install', '-r', path.join(rootDir, 'backend', 'requirements.txt'), 'pyinstaller']);
run(pyinstaller, [
  '--clean',
  '--noconfirm',
  '--onefile',
  '--name', 'cyclopscmd-backend',
  '--paths', path.join(rootDir, 'backend'),
  '--distpath', distDir,
  '--workpath', workDir,
  '--specpath', specDir,
  entryFile,
]);

fs.writeFileSync(path.join(distDir, '.gitkeep'), '');

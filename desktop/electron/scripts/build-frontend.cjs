const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const electronDir = path.resolve(__dirname, '..');
const rootDir = path.resolve(electronDir, '..', '..');
const npmCli = process.env.npm_execpath;

function runNpm(args) {
  if (npmCli && fs.existsSync(npmCli)) {
    console.log(`> ${process.execPath} ${npmCli} ${args.join(' ')}`);
    execFileSync(process.execPath, [npmCli, ...args], {
      cwd: rootDir,
      stdio: 'inherit',
    });
    return;
  }

  const command = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  console.log(`> ${command} ${args.join(' ')}`);
  execFileSync(command, args, {
    cwd: rootDir,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  });
}

// Electron loads the production bundle from file://, so asset URLs must be relative.
// Using Vite's CLI --base keeps normal Web/GitHub Pages builds unchanged.
runNpm(['run', 'build', '--', '--base=./']);

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

runNpm(['run', 'build', '--', '--base=./']);

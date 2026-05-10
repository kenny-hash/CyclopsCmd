const { execFileSync } = require('node:child_process');
const path = require('node:path');

const electronDir = path.resolve(__dirname, '..');
const rootDir = path.resolve(electronDir, '..', '..');
const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';

function run(command, args, options = {}) {
  console.log(`> ${command} ${args.join(' ')}`);
  execFileSync(command, args, { stdio: 'inherit', ...options });
}

// Electron loads the production bundle from file://, so asset URLs must be relative.
// Using Vite's CLI --base keeps normal Web/GitHub Pages builds unchanged.
run(npmCommand, ['run', 'build', '--', '--base=./'], { cwd: rootDir });

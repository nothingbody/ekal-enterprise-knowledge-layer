const { execFileSync } = require('child_process')
const fs = require('fs')
const path = require('path')

const desktopDir = path.resolve(__dirname, '..')
const backendDir = path.resolve(desktopDir, '..', 'backend')
const browsersDir = path.join(desktopDir, 'resources', 'ms-playwright')

fs.mkdirSync(browsersDir, { recursive: true })

const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const env = {
  ...process.env,
  PLAYWRIGHT_BROWSERS_PATH: browsersDir,
}

console.log(`Installing Playwright Chromium browsers into ${browsersDir}`)
execFileSync(python, ['-m', 'playwright', 'install', 'chromium'], {
  cwd: backendDir,
  env,
  stdio: 'inherit',
})

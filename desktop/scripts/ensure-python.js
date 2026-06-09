/**
 * 确保 Python 环境存在：开发模式检测 PATH，生产模式使用 bundled Python。
 * 生产版若已运行 download-python.js 构建，则使用 resources/python/。
 */
const { spawnSync } = require('child_process')
const fs = require('fs')
const path = require('path')

function findPythonInPath() {
  const cmds = process.platform === 'win32' ? ['python', 'python3', 'py -3'] : ['python3', 'python']
  for (const cmd of cmds) {
    try {
      const result = spawnSync(cmd, ['-c', 'import sys; print(sys.executable)'], {
        encoding: 'utf8',
        timeout: 3000,
      })
      if (result.status === 0 && result.stdout && result.stdout.trim()) {
        return result.stdout.trim()
      }
    } catch {}
  }
  return null
}

/**
 * 获取用于运行后端的 Python 路径。
 * @param {object} opts - { isDev, userDataPath, resourcesPath }
 * @returns {{ command: string, args: string[], cwd: string, pythonMissing?: boolean }}
 */
function getPythonForBackend(opts) {
  const { isDev, resourcesPath } = opts
  const backendDir = path.join(path.dirname(__dirname), '..', 'backend')
  const mainScript = path.join(backendDir, 'desktop_main.py')

  if (!isDev && resourcesPath) {
    const ext = process.platform === 'win32' ? '.exe' : ''
    const exePath = path.join(resourcesPath, 'backend', `desktop_main${ext}`)
    return {
      command: exePath,
      args: [],
      cwd: path.join(resourcesPath, 'backend'),
    }
  }

  let pythonExe = findPythonInPath()
  if (pythonExe) {
    return {
      command: pythonExe,
      args: [mainScript],
      cwd: backendDir,
    }
  }

  if (resourcesPath) {
    const bundled = process.platform === 'win32'
      ? path.join(resourcesPath, 'python', 'python.exe')
      : path.join(resourcesPath, 'python', 'bin', 'python3')
    if (fs.existsSync(bundled)) {
      return {
        command: bundled,
        args: [mainScript],
        cwd: backendDir,
      }
    }
  }

  return {
    command: 'python',
    args: [mainScript],
    cwd: backendDir,
    pythonMissing: true,
  }
}

/**
 * 获取用于沙箱的 Python 路径（供后端通过 env 使用）。
 * @param {object} opts - { isDev, resourcesPath }
 * @returns {string|null}
 */
function getPythonForSandbox(opts) {
  const { isDev, resourcesPath } = opts

  if (resourcesPath) {
    const bundled = process.platform === 'win32'
      ? path.join(resourcesPath, 'python', 'python.exe')
      : path.join(resourcesPath, 'python', 'bin', 'python3')
    if (fs.existsSync(bundled)) {
      return bundled
    }
  }

  const backend = getPythonForBackend(opts)
  if (backend.command && !backend.pythonMissing) {
    return backend.command
  }
  return null
}

module.exports = {
  findPythonInPath,
  getPythonForBackend,
  getPythonForSandbox,
}

const { app, BrowserWindow, shell, Tray, Menu, dialog, ipcMain } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')
const http = require('http')
const crypto = require('crypto')
const log = require('electron-log')
const { autoUpdater } = require('electron-updater')
const { getPythonForBackend, getPythonForSandbox } = require('./scripts/ensure-python')

process.on('uncaughtException', (err) => log.error('Uncaught exception:', err))
process.on('unhandledRejection', (reason) => log.error('Unhandled rejection:', reason))

const isDev = process.env.NODE_ENV === 'development'
const APP_NAME = '企业多模态知识协作共享服务平台'
const MAX_RESTART_ATTEMPTS = 2
const STARTUP_TIMEOUT_MS = 90000

if (!isDev && log.transports.console) {
  log.transports.console.level = false
}
if (log.transports.file) {
  log.transports.file.maxSize = 5 * 1024 * 1024
  log.transports.file.archiveLogFn = (oldFile) => {
    const info = path.parse(oldFile)
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    fs.renameSync(oldFile, path.join(info.dir, `${info.name}.${ts}${info.ext}`))
    const files = fs.readdirSync(info.dir)
      .filter(f => f.startsWith(info.name) && f !== `${info.name}${info.ext}`)
      .sort().reverse()
    files.slice(3).forEach(f => {
      try { fs.unlinkSync(path.join(info.dir, f)) } catch {}
    })
  }
}

function ignoreBrokenPipe(stream) {
  if (!stream || typeof stream.on !== 'function') return
  stream.on('error', (err) => {
    if (err && err.code === 'EPIPE') return
  })
}
ignoreBrokenPipe(process.stdout)
ignoreBrokenPipe(process.stderr)

function loadWindowState() {
  try {
    const statePath = path.join(app.getPath('userData'), 'window-state.json')
    if (fs.existsSync(statePath)) {
      return JSON.parse(fs.readFileSync(statePath, 'utf-8'))
    }
  } catch {}
  return null
}

function saveWindowState(win) {
  if (!win || win.isDestroyed()) return
  try {
    const bounds = win.getBounds()
    const isMaximized = win.isMaximized()
    const statePath = path.join(app.getPath('userData'), 'window-state.json')
    fs.writeFileSync(statePath, JSON.stringify({ ...bounds, isMaximized }), 'utf-8')
  } catch {}
}

let mainWindow = null
let splashWindow = null
let trayNoticeShown = false
let shutdownSecret = ''
let backendProcess = null
let frpcProcess = null
let publicTunnelUrl = null
let tray = null
let backendPort = null
let isQuitting = false
let isRestarting = false
let restartCount = 0

function isValidServerUrl(url) {
  if (!url || typeof url !== 'string') return false
  return /^https?:\/\/[^\s/$.?#].[^\s]*$/i.test(url.trim())
}

function getRemoteServerUrl() {
  if (process.env.REMOTE_SERVER_URL) {
    const url = process.env.REMOTE_SERVER_URL.replace(/\/+$/, '')
    if (isValidServerUrl(url)) return url
    log.warn('Invalid REMOTE_SERVER_URL:', process.env.REMOTE_SERVER_URL)
    return null
  }
  try {
    const configPath = path.join(app.getPath('userData'), 'server.json')
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      if (config.server_url) {
        const url = String(config.server_url).replace(/\/+$/, '')
        if (isValidServerUrl(url)) return url
        log.warn('Invalid server_url in server.json:', config.server_url)
      }
    }
  } catch (err) {
    log.warn('Failed to read/parse server.json:', err.message)
  }
  return null
}

function getBackendPath() {
  const resourcesPath = process.resourcesPath || path.join(__dirname, '..')
  return getPythonForBackend({
    isDev,
    resourcesPath,
  })
}

function getDesktopRuntimePaths() {
  const userDataPath = app.getPath('userData')
  return {
    desktopDataDir: path.join(userDataPath, 'data'),
    uploadDir: path.join(userDataPath, 'uploads'),
    frontendDistDir: isDev
      ? path.join(__dirname, '..', 'frontend', 'dist')
      : path.join(process.resourcesPath, 'frontend', 'dist'),
  }
}

/** 从 userData/central.json 注入中心连接参数（公网 IP 等），供 Python 子进程读取 */
function getCentralBackendEnv() {
  const out = {}
  try {
    const configPath = path.join(app.getPath('userData'), 'central.json')
    if (fs.existsSync(configPath)) {
      const j = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      if (j.server_public_ip) out.SERVER_PUBLIC_IP = String(j.server_public_ip).trim()
      if (j.central_server_url) out.CENTRAL_SERVER_URL = String(j.central_server_url).trim()
      if (j.central_server_scheme) out.CENTRAL_SERVER_SCHEME = String(j.central_server_scheme).trim()
      if (j.cloud_require_https === false) out.CLOUD_REQUIRE_HTTPS = 'false'
    }
  } catch (e) {
    log.warn('central.json:', e.message)
  }
  return out
}

function getLanSharingEnv(desktopDataDir) {
  const configPath = path.join(desktopDataDir, 'lan_sharing.json')
  try {
    if (fs.existsSync(configPath)) {
      const j = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      return { LAN_SHARING_ENABLED: j.enabled ? 'true' : 'false' }
    }
  } catch (e) {
    log.warn('lan_sharing.json:', e.message)
  }
  return { LAN_SHARING_ENABLED: 'false' }
}

function startBackend() {
  return new Promise((resolve, reject) => {
    const backendPath = getBackendPath()
    const { command, args, cwd, pythonMissing } = backendPath
    const { desktopDataDir, uploadDir, frontendDistDir } = getDesktopRuntimePaths()
    log.info(`Starting backend: ${command} ${args.join(' ')}`)

    if (pythonMissing && isDev) {
      const choice = dialog.showMessageBoxSync({
        type: 'warning',
        title: 'Python 未安装',
        message: '开发模式需要 Python 3.10+ 环境。',
        detail: '请从 python.org 下载安装 Python，或运行 npm run build:python 构建内置 Python 后使用生产模式。',
        buttons: ['打开 python.org', '退出'],
        defaultId: 0,
      })
      if (choice === 0) {
        shell.openExternal('https://www.python.org/downloads/')
      }
      reject(new Error('Python 未安装'))
      return
    }

    shutdownSecret = crypto.randomBytes(32).toString('hex')
    const resourcesPath = process.resourcesPath || path.join(__dirname, '..')
    const sandboxPython = getPythonForSandbox({ isDev, resourcesPath })
    const env = {
      ...getCentralBackendEnv(),
      ...getLanSharingEnv(desktopDataDir),
      ...process.env,
      DESKTOP_MODE: 'true',
      BACKEND_PORT: '0',
      DESKTOP_DATA_DIR: desktopDataDir,
      UPLOAD_DIR: uploadDir,
      FRONTEND_DIST_DIR: frontendDistDir,
      SHUTDOWN_SECRET: shutdownSecret,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
      ...(sandboxPython ? { SANDBOX_PYTHON_PATH: sandboxPython } : {}),
    }

    try {
      backendProcess = spawn(command, args, {
        cwd,
        env,
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      })
    } catch (spawnErr) {
      log.error('Failed to spawn backend process:', spawnErr)
      reject(new Error(`无法启动后端进程: ${spawnErr.message}`))
      return
    }

    let portFound = false
    let stderrBuffer = ''
    let stdoutBuffer = ''
    let timeoutId = null

    function cleanup() {
      if (timeoutId) { clearTimeout(timeoutId); timeoutId = null }
    }

    backendProcess.stdout.on('data', (data) => {
      const output = data.toString()
      stdoutBuffer += output
      log.info(`[backend] ${output.trim()}`)

      const errMatch = stdoutBuffer.match(/@@ERROR@@(.+?)@@ERROR@@/s)
      if (errMatch && !portFound) {
        cleanup()
        reject(new Error(`后端启动失败: ${errMatch[1].trim()}`))
        return
      }

      const portMatch = stdoutBuffer.match(/@@PORT@@(\d+)@@PORT@@/)
      if (portMatch && !portFound) {
        portFound = true
        cleanup()
        backendPort = parseInt(portMatch[1], 10)
        log.info(`Backend port detected: ${backendPort}`)
        resolve(backendPort)
      }
    })

    backendProcess.stderr.on('data', (data) => {
      const msg = data.toString().trim()
      stderrBuffer += msg + '\n'
      log.warn(`[backend:err] ${msg}`)
    })

    backendProcess.on('error', (err) => {
      log.error('Failed to start backend:', err)
      if (!portFound) { cleanup(); reject(err) }
    })

    backendProcess.on('exit', (code, signal) => {
      log.info(`Backend exited: code=${code}, signal=${signal}`)
      backendProcess = null
      if (!portFound && !isQuitting) {
        cleanup()
        const errDetail = stderrBuffer.trim() ? `\n后端日志:\n${stderrBuffer.trim().slice(-500)}` : ''
        reject(new Error(`后端进程已退出 (code=${code})${errDetail}`))
      } else if (!isQuitting && mainWindow) {
        handleBackendCrash(code)
      }
    })

    timeoutId = setTimeout(() => {
      if (!portFound) {
        const errDetail = stderrBuffer.trim() ? `\n后端日志:\n${stderrBuffer.trim().slice(-500)}` : ''
        reject(new Error(`后端启动超时 (${STARTUP_TIMEOUT_MS / 1000}秒)${errDetail}`))
      }
    }, STARTUP_TIMEOUT_MS)
  })
}

async function handleBackendCrash(exitCode) {
  if (isQuitting || isRestarting) return
  isRestarting = true
  log.warn(`Backend crashed (code=${exitCode}), restart attempt ${restartCount + 1}/${MAX_RESTART_ATTEMPTS}`)

  if (restartCount < MAX_RESTART_ATTEMPTS) {
    restartCount++
    try {
      await startBackend()
      await waitForHealth(`http://127.0.0.1:${backendPort}`)
      log.info(`Backend restarted successfully (attempt ${restartCount})`)
      if (mainWindow) {
        mainWindow.loadURL(`http://127.0.0.1:${backendPort}`).catch(() => {})
      }
      restartCount = 0
    } catch (err) {
      log.error(`Backend restart failed (attempt ${restartCount}):`, err)
      dialog.showErrorBox('后端服务异常', `后端服务多次重启失败，应用将关闭。\n\n${err.message}`)
      isQuitting = true
      app.quit()
    } finally {
      isRestarting = false
    }
  } else {
    isRestarting = false
    dialog.showErrorBox('后端进程异常退出', `后端服务已停止 (code: ${exitCode})，多次重启失败。应用将关闭。`)
    isQuitting = true
    app.quit()
  }
}

function stopBackend() {
  const proc = backendProcess
  if (!proc) return Promise.resolve()
  log.info('Stopping backend process...')
  isQuitting = true

  if (backendPort && shutdownSecret) {
    const req = http.get(`http://127.0.0.1:${backendPort}/api/shutdown`, {
      headers: { 'X-Shutdown-Token': shutdownSecret },
    }, () => {})
    req.on('error', () => {})
    req.setTimeout(1000, () => req.destroy())
  }

  const pid = proc.pid
  return new Promise((resolve) => {
    let resolved = false
    const finish = () => {
      if (resolved) return
      resolved = true
      backendProcess = null
      resolve()
    }

    proc.once('exit', finish)

    // Give the graceful shutdown 3 seconds, then force kill
    setTimeout(() => {
      if (resolved) return
      try {
        if (process.platform === 'win32') {
          const kill = spawn('taskkill', ['/pid', pid.toString(), '/f', '/t'])
          kill.on('exit', () => { setTimeout(finish, 300) })
          kill.on('error', () => { setTimeout(finish, 300) })
        } else {
          process.kill(pid, 'SIGKILL')
          setTimeout(finish, 300)
        }
      } catch {
        finish()
      }
      // Final safety timeout
      setTimeout(finish, 2000)
    }, 3000)
  })
}

function waitForHealth(baseUrl, maxRetries = 120) {
  return new Promise((resolve, reject) => {
    let attempts = 0
    const isHttps = baseUrl.startsWith('https')
    const httpModule = isHttps ? require('https') : http

    function check() {
      attempts++
      if (attempts % 10 === 0) {
        log.info(`Health check attempt ${attempts}/${maxRetries}...`)
      }
      // 统一部署 Nginx：`/api/v1/` → 节点后端；`/api/` 无 `/v1` 时可能落到中心服。与前端 axios 的 `/api/v1` 一致。
      const req = httpModule.get(`${baseUrl}/api/v1/health`, (res) => {
        let body = ''
        res.on('data', (chunk) => { body += chunk })
        res.on('end', () => {
          if (res.statusCode === 200) {
            try {
              const data = JSON.parse(body)
              if (data.status === 'ok' || data.status === 'degraded' || data.database) {
                log.info(`Health check passed on attempt ${attempts}`)
                resolve()
                return
              }
            } catch {}
            // Accept 200 even if body is not JSON (legacy)
            log.info(`Health check passed on attempt ${attempts} (status 200)`)
            resolve()
          } else if (attempts < maxRetries) {
            setTimeout(check, 500)
          } else {
            reject(new Error(`Health check failed: status ${res.statusCode}`))
          }
        })
      })
      req.on('error', () => {
        if (attempts < maxRetries) setTimeout(check, 500)
        else reject(new Error(`Server unreachable after ${maxRetries} attempts`))
      })
      req.setTimeout(3000, () => {
        req.destroy()
        if (attempts < maxRetries) setTimeout(check, 500)
      })
    }

    setTimeout(check, 1000)
  })
}

function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 400,
    height: 300,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  })
  splashWindow.loadFile(path.join(__dirname, 'splash.html'))
  splashWindow.center()
}

function createMainWindow(url) {
  const savedState = loadWindowState()
  mainWindow = new BrowserWindow({
    width: savedState?.width || 1400,
    height: savedState?.height || 900,
    x: savedState?.x,
    y: savedState?.y,
    minWidth: 900,
    minHeight: 600,
    title: APP_NAME,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  })
  if (savedState?.isMaximized) mainWindow.maximize()

  mainWindow.setMenuBarVisibility(false)
  log.info(`Loading frontend from: ${url}`)

  let windowShown = false
  function ensureWindowVisible() {
    if (windowShown) return
    windowShown = true
    if (splashWindow) { splashWindow.close(); splashWindow = null }
    mainWindow.show()
    mainWindow.focus()
    log.info('Main window shown')
  }

  mainWindow.loadURL(url).catch((err) => {
    log.error('Failed to load URL:', err)
    ensureWindowVisible()
  })

  mainWindow.once('ready-to-show', () => {
    log.info('ready-to-show event fired')
    ensureWindowVisible()
  })

  setTimeout(() => {
    if (!windowShown) {
      log.warn('ready-to-show timeout — forcing window visible')
      ensureWindowVisible()
    }
  }, 10000)

  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
    log.error(`Page load failed: ${errorCode} ${errorDescription}`)
    ensureWindowVisible()
  })

  mainWindow.webContents.setWindowOpenHandler(({ url: linkUrl }) => {
    shell.openExternal(linkUrl)
    return { action: 'deny' }
  })

  mainWindow.on('resize', () => saveWindowState(mainWindow))
  mainWindow.on('move', () => saveWindowState(mainWindow))

  mainWindow.on('close', (e) => {
    saveWindowState(mainWindow)
    if (!isQuitting) {
      e.preventDefault()
      mainWindow.hide()
      if (!trayNoticeShown && tray) {
        tray.displayBalloon({
          title: APP_NAME,
          content: '程序已最小化到系统托盘，双击托盘图标可恢复窗口。',
          iconType: 'info',
        })
        trayNoticeShown = true
      }
    }
  })

  mainWindow.on('closed', () => { mainWindow = null })

  // F12 或 Ctrl+Shift+I 打开开发者工具
  mainWindow.webContents.on('before-input-event', (_event, input) => {
    if (input.key === 'F12' || (input.control && input.shift && input.key === 'I')) {
      mainWindow.webContents.toggleDevTools()
    }
  })

  if (isDev) {
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  }
}

function createTray() {
  let iconPath = path.join(__dirname, 'icon.png')
  if (!fs.existsSync(iconPath)) {
    const logoPath = path.join(__dirname, '..', 'doc', 'logo.png')
    if (fs.existsSync(logoPath)) {
      iconPath = logoPath
    } else {
      log.warn('Tray icon not found, skipping tray creation')
      return
    }
  }
  try {
    tray = new Tray(iconPath)
  } catch (err) {
    log.warn('Failed to create tray:', err.message)
    return
  }

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示主窗口',
      click: () => {
        if (mainWindow) { mainWindow.show(); mainWindow.focus() }
      },
    },
    {
      label: '检查更新',
      click: () => {
        autoUpdater.checkForUpdates().then((result) => {
          if (!result || !result.updateInfo || result.updateInfo.version === app.getVersion()) {
            dialog.showMessageBox({ type: 'info', title: '检查更新', message: `当前已是最新版本 (v${app.getVersion()})。` })
          }
        }).catch((err) => {
          log.warn('Manual update check failed:', err.message)
          dialog.showMessageBox({ type: 'info', title: '检查更新', message: '检查更新失败，请检查网络连接。' })
        })
      },
    },
    {
      label: '打开日志',
      click: () => {
        const logPath = log.transports.file.getFile().path
        shell.showItemInFolder(logPath)
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => { isQuitting = true; app.quit() },
    },
  ])

  tray.setToolTip(APP_NAME)
  tray.setContextMenu(contextMenu)
  tray.on('double-click', () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus() }
  })
}

// ── FRP Tunnel ──
const FRP_SERVER = process.env.FRP_SERVER || ''
const FRP_SERVER_PORT = Number(process.env.FRP_SERVER_PORT || 7000)
// FRP is disabled unless both FRP_SERVER and FRP_TOKEN are supplied by the runtime environment.
function _getFrpToken() {
  return process.env.FRP_TOKEN || ''
}
const FRP_TOKEN = _getFrpToken()

function getFrpcPath() {
  if (isDev) return null
  const frpcPath = path.join(process.resourcesPath, 'frpc.exe')
  return fs.existsSync(frpcPath) ? frpcPath : null
}

function startFrpTunnel(localPort) {
  if (!FRP_SERVER || !FRP_TOKEN) {
    log.info('FRP_SERVER or FRP_TOKEN not configured, skipping tunnel')
    return
  }

  const frpcPath = getFrpcPath()
  if (!frpcPath) {
    log.info('frpc not found, skipping tunnel')
    return
  }

  // Random remote port between 10000-15000
  const remotePort = 10000 + Math.floor(Math.random() * 5000)

  const configContent = [
    'serverAddr = "' + FRP_SERVER + '"',
    'serverPort = ' + FRP_SERVER_PORT,
    'auth.method = "token"',
    'auth.token = "' + FRP_TOKEN + '"',
    '',
    '[[proxies]]',
    'name = "zhishu-' + remotePort + '"',
    'type = "tcp"',
    'localIP = "127.0.0.1"',
    'localPort = ' + localPort,
    'remotePort = ' + remotePort,
  ].join('\n')

  const configPath = path.join(app.getPath('userData'), 'frpc.toml')
  fs.writeFileSync(configPath, configContent, 'utf-8')

  try {
    frpcProcess = spawn(frpcPath, ['-c', configPath], {
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })

    frpcProcess.stdout.on('data', (data) => {
      const msg = data.toString().trim()
      log.info(`[frpc] ${msg}`)
      if (msg.includes('start proxy success')) {
        publicTunnelUrl = `http://${FRP_SERVER}:${remotePort}`
        log.info(`Tunnel established: ${publicTunnelUrl}`)
        // Write tunnel URL for backend to read
        try {
          const tunnelFile = path.join(app.getPath('userData'), 'data', '.tunnel_url')
          fs.mkdirSync(path.dirname(tunnelFile), { recursive: true })
          fs.writeFileSync(tunnelFile, publicTunnelUrl, 'utf-8')
        } catch {}
      }
    })

    frpcProcess.stderr.on('data', (data) => {
      log.warn(`[frpc:err] ${data.toString().trim()}`)
    })

    frpcProcess.on('exit', (code) => {
      log.info(`frpc exited: code=${code}`)
      frpcProcess = null
      if (!isQuitting) {
        // Retry after 10s
        setTimeout(() => {
          if (!isQuitting && backendPort) startFrpTunnel(backendPort)
        }, 10000)
      }
    })

    frpcProcess.on('error', (err) => {
      log.warn('frpc spawn error:', err.message)
      frpcProcess = null
    })

    log.info(`frpc started: local=${localPort} -> remote=${FRP_SERVER}:${remotePort}`)
  } catch (err) {
    log.warn('Failed to start frpc:', err.message)
  }
}

function stopFrpTunnel() {
  if (!frpcProcess) return
  try {
    frpcProcess.kill()
  } catch {}
  frpcProcess = null
  publicTunnelUrl = null
}

// ── App Lifecycle ──
app.whenReady().then(async () => {
  log.info(`${APP_NAME} starting...`)
  const remoteUrl = getRemoteServerUrl()

  createSplashWindow()

  if (remoteUrl) {
    log.info(`Remote mode: connecting to ${remoteUrl}`)
    try {
      await waitForHealth(remoteUrl, 20)
      log.info('Remote server is reachable')
    } catch (err) {
      log.error('Remote server unreachable:', err)
      if (splashWindow) splashWindow.close()
      dialog.showErrorBox('连接失败', `无法连接到服务器：\n${remoteUrl}\n\n${err.message}`)
      app.quit()
      return
    }
    createMainWindow(remoteUrl)
  } else {
    try {
      await startBackend()
      log.info(`Backend started on port ${backendPort}`)
      await waitForHealth(`http://127.0.0.1:${backendPort}`)
      log.info('Backend health check passed')
      createMainWindow(`http://127.0.0.1:${backendPort}`)
      // Start frp tunnel for public sharing
      startFrpTunnel(backendPort)
    } catch (err) {
      log.error('Startup failed:', err)
      if (splashWindow) splashWindow.close()
      dialog.showErrorBox('启动失败', `后端服务启动失败：\n${err.message}\n\n请检查日志或联系技术支持。`)
      app.quit()
      return
    }
  }

  createTray()
  setupAutoUpdater()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    isQuitting = true
    app.quit()
  }
})

app.on('activate', () => {
  if (mainWindow) mainWindow.show()
})

app.on('before-quit', async (e) => {
  isQuitting = true
  stopFrpTunnel()
  if (backendProcess) {
    e.preventDefault()
    await stopBackend()
    app.quit()
  }
})

// ── Auto Update ──
autoUpdater.logger = log
autoUpdater.autoDownload = false
autoUpdater.autoInstallOnAppQuit = true

const customUpdateUrl = getRemoteServerUrl()
if (customUpdateUrl && /^https?:\/\//.test(customUpdateUrl)) {
  const updateUrl = customUpdateUrl.replace(/^http:\/\//, 'https://') + '/downloads'
  autoUpdater.setFeedURL({ provider: 'generic', url: updateUrl })
  log.info('Auto-update URL set to:', updateUrl)
}

let _autoUpdateSetup = false
let _isDownloading = false

function setupAutoUpdater() {
  if (_autoUpdateSetup) return
  _autoUpdateSetup = true

  autoUpdater.on('update-available', (info) => {
    log.info('Update available:', info.version)
    if (mainWindow && !_isDownloading) {
      dialog.showMessageBox(mainWindow, {
        type: 'info',
        title: '发现新版本',
        message: `发现新版本 v${info.version}，是否立即下载？`,
        buttons: ['稍后', '立即下载'],
        defaultId: 0,
      }).then(({ response }) => {
        if (response === 1 && !_isDownloading) {
          _isDownloading = true
          autoUpdater.downloadUpdate()
        }
      })
    }
  })

  autoUpdater.on('update-not-available', () => log.info('No update available'))

  autoUpdater.on('download-progress', (progress) => {
    log.info(`Download progress: ${Math.round(progress.percent)}%`)
  })

  autoUpdater.on('update-downloaded', (info) => {
    log.info('Update downloaded:', info.version)
    _isDownloading = false
    if (mainWindow) {
      dialog.showMessageBox(mainWindow, {
        type: 'info',
        title: '更新就绪',
        message: `v${info.version} 已下载完成，是否立即安装并重启？`,
        buttons: ['下次启动时安装', '立即安装'],
        defaultId: 0,
      }).then(({ response }) => {
        if (response === 1) { isQuitting = true; autoUpdater.quitAndInstall() }
      })
    }
  })

  autoUpdater.on('error', (err) => log.error('Auto-update error:', err))

  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((err) => log.warn('Update check failed:', err.message))
  }, 10000)

  setInterval(() => {
    autoUpdater.checkForUpdates().catch(() => {})
  }, 4 * 60 * 60 * 1000)
}

// ── IPC Handlers ──
ipcMain.handle('check-for-updates', async () => {
  try {
    const result = await autoUpdater.checkForUpdates()
    return { updateAvailable: !!result?.updateInfo, version: result?.updateInfo?.version }
  } catch {
    return { updateAvailable: false }
  }
})

ipcMain.handle('get-app-version', () => app.getVersion())

ipcMain.handle('get-log-path', () => {
  try {
    return log.transports.file.getFile().path
  } catch {
    return null
  }
})

ipcMain.handle('open-log-folder', () => {
  try {
    const logPath = log.transports.file.getFile().path
    shell.showItemInFolder(logPath)
  } catch (err) {
    log.warn('Failed to get log path:', err.message)
  }
})

ipcMain.handle('get-backend-info', () => ({
  port: backendPort,
  isRemote: !!getRemoteServerUrl(),
  running: !!backendProcess,
  tunnelUrl: publicTunnelUrl,
}))

// Prevent multiple instances
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

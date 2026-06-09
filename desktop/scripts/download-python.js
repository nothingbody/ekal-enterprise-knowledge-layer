/**
 * 构建时下载 Python embeddable 并解压到 resources/python/
 * 用于桌面版沙箱，当系统无 Python 时使用 bundled 版本。
 * 运行: node scripts/download-python.js
 */
const fs = require('fs')
const path = require('path')
const https = require('https')

const DESKTOP_DIR = path.resolve(__dirname, '..')
const RESOURCES_DIR = path.join(DESKTOP_DIR, 'resources', 'python')
const PYTHON_VERSION = '3.12.2'

const PLATFORM_URLS = {
  win32: `https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip`,
  // macOS/Linux 可后续添加 python-build-standalone 等
}

function download(url) {
  return new Promise((resolve, reject) => {
    const chunks = []
    https.get(url, { redirect: true }, (res) => {
      if (res.statusCode === 301 || res.statusCode === 302) {
        return download(res.headers.location).then(resolve).catch(reject)
      }
      res.on('data', (c) => chunks.push(c))
      res.on('end', () => resolve(Buffer.concat(chunks)))
      res.on('error', reject)
    }).on('error', reject)
  })
}

function extractZip(buf, outDir) {
  try {
    const AdmZip = require('adm-zip')
    const zip = new AdmZip(buf)
    zip.extractAllTo(outDir, true)
    return true
  } catch (e) {
    console.warn('adm-zip 不可用，尝试 PowerShell 解压...')
    const zipPath = path.join(DESKTOP_DIR, 'python-embed-temp.zip')
    fs.writeFileSync(zipPath, buf)
    try {
      const { execSync } = require('child_process')
      execSync(`powershell -Command "Expand-Archive -Path '${zipPath}' -DestinationPath '${outDir}' -Force"`, { stdio: 'inherit' })
      fs.unlinkSync(zipPath)
      return true
    } catch (e2) {
      if (fs.existsSync(zipPath)) fs.unlinkSync(zipPath)
      return false
    }
  }
}

async function main() {
  fs.mkdirSync(RESOURCES_DIR, { recursive: true })

  const platform = process.platform
  const url = PLATFORM_URLS[platform]
  if (!url) {
    console.log(`跳过: 平台 ${platform} 暂无预置 Python 下载`)
    return
  }

  const pythonExe = path.join(RESOURCES_DIR, platform === 'win32' ? 'python.exe' : 'bin/python3')
  if (fs.existsSync(pythonExe)) {
    console.log('Python 已存在:', pythonExe)
    return
  }

  console.log('正在下载 Python embeddable...')
  const buf = await download(url)
  fs.mkdirSync(RESOURCES_DIR, { recursive: true })
  if (extractZip(buf, RESOURCES_DIR)) {
    console.log('Python 已解压到:', RESOURCES_DIR)
  } else {
    console.error('解压失败')
    process.exit(1)
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})

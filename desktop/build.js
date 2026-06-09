/**
 * Full build script for the RAG Platform desktop application.
 * 
 * Steps:
 *   1. Build frontend (vite build)
 *   2. Bundle backend (PyInstaller)
 *   3. Package with electron-builder
 * 
 * Usage:
 *   node build.js          — build all, then package
 *   node build.js --dev    — build all without packaging (for local testing)
 */
const { execSync } = require('child_process')
const path = require('path')
const fs = require('fs')

const ROOT = path.resolve(__dirname, '..')
const FRONTEND = path.join(ROOT, 'frontend')
const BACKEND = path.join(ROOT, 'backend')
const DESKTOP = __dirname

const isDev = process.argv.includes('--dev')

function run(cmd, cwd, label) {
  console.log(`\n${'═'.repeat(50)}`)
  console.log(`  ${label}`)
  console.log(`${'═'.repeat(50)}`)
  console.log(`> ${cmd}\n`)
  execSync(cmd, { cwd, stdio: 'inherit', shell: true })
}

try {
  // 1. Build frontend
  run('npm run build', FRONTEND, '📦 Building Frontend (Vite)')

  // 2. Verify frontend dist exists
  const distDir = path.join(FRONTEND, 'dist', 'index.html')
  if (!fs.existsSync(distDir)) {
    throw new Error('Frontend build failed: dist/index.html not found')
  }
  console.log('✓ Frontend build complete')

  // 3. Bundle backend with PyInstaller
  run('pyinstaller --noconfirm desktop_main.spec', BACKEND, '📦 Bundling Backend (PyInstaller)')

  const backendExe = path.join(BACKEND, 'dist', 'desktop_main',
    process.platform === 'win32' ? 'desktop_main.exe' : 'desktop_main')
  if (!fs.existsSync(backendExe)) {
    throw new Error(`Backend bundle failed: ${backendExe} not found`)
  }
  console.log('✓ Backend bundle complete')

  // 4. Package with electron-builder (unless --dev)
  if (!isDev) {
    run('npx electron-builder', DESKTOP, '📦 Packaging Desktop App (electron-builder)')
    console.log('\n✅ Desktop app packaged successfully! Check desktop/release/')
  } else {
    console.log('\n✅ Dev build complete. Run "npm run dev" (or "npm start") in desktop/ to test.')
  }

} catch (err) {
  console.error(`\n❌ Build failed: ${err.message}`)
  process.exit(1)
}

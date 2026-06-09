const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktopAPI', {
  platform: process.platform,
  isDesktop: true,
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  getVersion: () => ipcRenderer.invoke('get-app-version'),
  getLogPath: () => ipcRenderer.invoke('get-log-path'),
  openLogFolder: () => ipcRenderer.invoke('open-log-folder'),
  getBackendInfo: () => ipcRenderer.invoke('get-backend-info'),
})

// API base URL for all requests.
// In development: empty string (Vite proxy handles /api → backend)
// In production with nginx reverse proxy: empty string (same-origin)
// In production cross-origin: set VITE_API_BASE_URL to backend URL,
//   e.g. VITE_API_BASE_URL=https://api.example.com
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  ? (import.meta.env.VITE_API_BASE_URL as string).replace(/\/+$/, '')
  : ''

export const API_V1 = `${API_BASE_URL}/api/v1`

/**
 * Get the actual backend origin for constructing external-facing URLs
 * (Webhook URLs, share links, etc.). Falls back to window.location.origin.
 */
let _cachedBackendOrigin: string | null = null
export function getBackendOrigin(): string {
  if (_cachedBackendOrigin) return _cachedBackendOrigin
  if (API_BASE_URL) {
    _cachedBackendOrigin = API_BASE_URL
    return API_BASE_URL
  }
  _cachedBackendOrigin = window.location.origin
  return _cachedBackendOrigin
}

/**
 * Get the base URL for share/public links.
 * Priority: tunnel URL (public) > LAN IP > localhost
 */
let _cachedShareBaseUrl = ''
export function getShareBaseUrl(): string {
  if (_cachedShareBaseUrl) return _cachedShareBaseUrl
  const origin = window.location.origin

  // Desktop mode: try tunnel URL first (public internet access)
  if ((window as any).desktopAPI) {
    try {
      const xhr = new XMLHttpRequest()
      xhr.open('GET', `${API_V1}/system/tunnel-info`, false)
      const token = localStorage.getItem('token')
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      xhr.send()
      if (xhr.status === 200) {
        const data = JSON.parse(xhr.responseText)
        if (data.tunnel_url) {
          _cachedShareBaseUrl = data.tunnel_url
          return _cachedShareBaseUrl
        }
        if (data.lan_ip && data.lan_sharing_enabled) {
          const port = window.location.port
          _cachedShareBaseUrl = `http://${data.lan_ip}${port ? ':' + port : ''}`
          return _cachedShareBaseUrl
        }
      }
    } catch {}
  }
  return origin
}

export function setShareBaseUrl(url: string): void {
  _cachedShareBaseUrl = url || ''
}

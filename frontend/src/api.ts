import { resolveApiBase } from './api-config.js'

const API_BASE = resolveApiBase(import.meta.env.VITE_API_BASE_URL, import.meta.env.DEV, window.location.hostname)

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase()
  if (!API_BASE) {
    console.error('[ONPay API] VITE_API_BASE_URL is missing from this production build', { method, path })
    throw new ApiError('ONPay is not connected to its server yet. Please try again later.', 0)
  }
  let url: URL
  try {
    url = new URL(path, `${API_BASE}/`)
  } catch {
    console.error('[ONPay API] VITE_API_BASE_URL is invalid', { method, path })
    throw new ApiError('ONPay’s server address is not configured correctly. Please try again later.', 0)
  }
  if (window.location.protocol === 'https:' && url.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(url.hostname)) {
    console.error('[ONPay API] HTTPS page is configured with a non-HTTPS API URL', { method, origin: url.origin, path: url.pathname })
    throw new ApiError('ONPay’s server must use a secure HTTPS connection. Please try again later.', 0)
  }

  let response: Response
  try {
    response = await fetch(url.toString(), {
      ...options,
      credentials: 'include',
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    })
  } catch (error) {
    console.error('[ONPay API] Network request failed before an HTTP response', {
      method,
      origin: url.origin,
      path: url.pathname,
      errorType: error instanceof Error ? error.name : 'UnknownError',
    })
    throw new ApiError('Could not connect to ONPay. Check your internet connection and try again.', 0)
  }

  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await response.json().catch(() => null) : null
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : `ONPay’s server returned an error (${response.status}).`
    throw new ApiError(message, response.status)
  }
  if (data === null) {
    console.error('[ONPay API] Server returned a non-JSON response', { method, origin: url.origin, path: url.pathname, status: response.status })
    throw new ApiError('ONPay received an unexpected response from its server. Please try again later.', response.status)
  }
  return data as T
}

export const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })
export const patch = (body: unknown): RequestInit => ({ method: 'PATCH', body: JSON.stringify(body) })

declare global {
  interface ImportMetaEnv { readonly VITE_API_BASE_URL?: string }
  interface ImportMeta { readonly env: ImportMetaEnv }
}

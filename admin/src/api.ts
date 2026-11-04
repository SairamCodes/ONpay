export interface AdminUser {
  id: string
  email: string
  role: string
  created_at: string
}

export interface KPIStats {
  total_users: number
  total_successful_daily_logins: number
  unique_daily_active_users: number
  completed_transactions: number
  completed_transaction_volume: number
  total_points_awarded: number
  pending_subscriptions: number
  active_subscriptions: number
}

export interface DailyTrendItem {
  date: string
  logins: number
  unique_users: number
  volume?: number
  completed_tx?: number
}
export interface AnalyticsResponse extends KPIStats {
  trend_14d: DailyTrendItem[]
}

export interface UserSummary {
  id: string
  name: string
  email: string
  phone: string
  college: string
  points: number
  plan: string
  last_login_at: string | null
  created_at: string
}

export interface ExchangeSummary {
  id: string
  amount: number
  mode: string
  status: string
  seeker_name: string
  seeker_email: string
  provider_name: string
  provider_email: string
  seeker_cash_received: boolean
  provider_upi_received: boolean
  completed_at: string | null
  created_at: string
}

export interface PointLedgerEntry {
  id: string
  user_id: string
  user_name: string
  user_email: string
  amount: number
  balance_after: number
  reason: string
  reference_id: string | null
  created_at: string
}

export interface QRCodeItem {
  id: string
  upi_id: string
  image_url: string
  is_active: boolean
  created_at: string
  admin_id: string
}

export interface SubscriptionRequestItem {
  id: string
  user_id: string
  user_name: string
  user_email: string
  plan_name: string
  amount: number
  upi_ref: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  rejection_reason: string | null
  has_proof: boolean
  target_review_minutes: number
  elapsed_seconds: number
  is_overdue: boolean
  created_at: string
  reviewed_at: string | null
}

export interface AuditLogItem {
  id: string
  admin_id: string
  action: string
  target_type: string
  target_id: string | null
  details: string
  ip_address: string | null
  created_at: string
}

const TOKEN_KEY = 'onpay_admin_token'
const RAW_API_BASE = ((import.meta.env.VITE_API_BASE_URL as string | undefined) || '').trim().replace(/\/+$/, '')

export function resolveAdminUrl(endpoint: string): string {
  if (!RAW_API_BASE) {
    // Preserve local Vite proxy (/api -> http://localhost:8000) or relative reverse-proxy routing
    return endpoint
  }
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`
  return `${RAW_API_BASE}${cleanEndpoint}`
}

export function getAdminToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAdminToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearAdminToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export async function adminFetch(endpoint: string, options: RequestInit = {}): Promise<any> {
  const token = getAdminToken()
  const headers = new Headers(options.headers || {})

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const url = resolveAdminUrl(endpoint)
  const res = await fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (res.status === 401) {
    clearAdminToken()
    window.dispatchEvent(new CustomEvent('onpay-admin-unauthorized'))
    throw new Error('Unauthorized or session expired')
  }

  if (!res.ok) {
    let errorDetail = 'API request failed'
    try {
      const errJson = await res.json()
      if (errJson.detail) errorDetail = errJson.detail
    } catch {
      errorDetail = await res.text() || res.statusText
    }
    throw new Error(errorDetail)
  }

  return res.json()
}

export const api = {
  async login(email: string, password: string) {
    const data = await adminFetch('/api/admin/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (data.session_token) {
      setAdminToken(data.session_token)
    }
    return data
  },
async getMe(): Promise<AdminUser> {
  return adminFetch('/api/admin/auth/me')
},
  async logout(): Promise<void> {
    try {
      await adminFetch('/api/admin/auth/logout', { method: 'POST' })
    } finally {
      clearAdminToken()
    }
  },

  async getAnalytics(days: number = 14): Promise<AnalyticsResponse> {
    return adminFetch(`/api/admin/analytics?days=${days}`)
  },

  async getUsers(search: string = '', page: number = 1, limit: number = 30): Promise<{
    users: UserSummary[]
    total: number
    page: number
    pages: number
  }> {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    params.set('page', page.toString())
    params.set('limit', limit.toString())
    return adminFetch(`/api/admin/users?${params.toString()}`)
  },

  async getUserDetail(userId: string): Promise<{
    user: UserSummary
    exchanges: ExchangeSummary[]
    ledger: PointLedgerEntry[]
  }> {
    return adminFetch(`/api/admin/users/${userId}`)
  },

  async getTransactions(statusFilter: string = '', search: string = '', page: number = 1, limit: number = 30): Promise<{
    transactions: ExchangeSummary[]
    total: number
    page: number
    pages: number
  }> {
    const params = new URLSearchParams()
    if (statusFilter) params.set('status_filter', statusFilter)
    if (search) params.set('search', search)
    params.set('page', page.toString())
    params.set('limit', limit.toString())
    return adminFetch(`/api/admin/transactions?${params.toString()}`)
  },

  async getPointsLedger(userId: string = '', searchReason: string = '', page: number = 1, limit: number = 30): Promise<{
    entries: PointLedgerEntry[]
    total: number
    page: number
    pages: number
  }> {
    const params = new URLSearchParams()
    if (userId) params.set('user_id', userId)
    if (searchReason) params.set('search_reason', searchReason)
    params.set('page', page.toString())
    params.set('limit', limit.toString())
    return adminFetch(`/api/admin/points/ledger?${params.toString()}`)
  },

  async adjustPoints(userId: string, amount: number, reason: string): Promise<any> {
    return adminFetch(`/api/admin/users/${userId}/points/adjust`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount, reason }),
    })
  },

  async getQRCodes(): Promise<{ qr_codes: QRCodeItem[] }> {
    return adminFetch('/api/admin/qr-codes')
  },

  async uploadQRCode(file: File, upiId: string): Promise<any> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('upi_id', upiId)
    const token = getAdminToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch('/api/admin/qr-codes', {
      method: 'POST',
      headers,
      credentials: 'include',
      body: formData,
    })
    if (!res.ok) {
      let err = 'Upload failed'
      try {
        const j = await res.json()
        if (j.detail) err = j.detail
      } catch {
        err = await res.text() || res.statusText
      }
      throw new Error(err)
    }
    return res.json()
  },

  async activateQRCode(qrId: string): Promise<any> {
    return adminFetch(`/api/admin/qr-codes/${qrId}/activate`, {
      method: 'PUT',
    })
  },

  async getSubscriptions(statusFilter: string = '', page: number = 1, limit: number = 30): Promise<{
    requests: SubscriptionRequestItem[]
    total: number
    page: number
    pages: number
  }> {
    const params = new URLSearchParams()
    if (statusFilter) params.set('status_filter', statusFilter)
    params.set('page', page.toString())
    params.set('limit', limit.toString())
    return adminFetch(`/api/admin/subscriptions?${params.toString()}`)
  },

  async approveSubscription(reqId: string): Promise<any> {
    return adminFetch(`/api/admin/subscriptions/${reqId}/approve`, {
      method: 'POST',
    })
  },

  async rejectSubscription(reqId: string, reason: string): Promise<any> {
    return adminFetch(`/api/admin/subscriptions/${reqId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
  },

  async getAuditLogs(actionFilter: string = '', page: number = 1, limit: number = 50): Promise<{
    logs: AuditLogItem[]
    total: number
    page: number
    pages: number
  }> {
    const params = new URLSearchParams()
    if (actionFilter) params.set('action_filter', actionFilter)
    params.set('page', page.toString())
    params.set('limit', limit.toString())
    return adminFetch(`/api/admin/audit-logs?${params.toString()}`)
  },
}

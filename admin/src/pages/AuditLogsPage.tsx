import React, { useEffect, useState } from 'react'
import { api, AuditLogItem } from '../api'

export const AuditLogsPage: React.FC = () => {
  const [logs, setLogs] = useState<AuditLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [actionFilter, setActionFilter] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadLogs = async () => {
    try {
      setLoading(true)
      const res = await api.getAuditLogs(actionFilter, page, 40)
      setLogs(res.logs)
      setTotal(res.total)
    } catch (err: any) {
      setError(err.message || 'Failed to load audit logs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLogs()
  }, [page, actionFilter])

  return (
    <div>
      <div className="section-card">
        <div className="section-header">
          <h3 className="section-title">Administrative Audit Trail ({total})</h3>
          <div style={{ display: 'flex', gap: '12px' }}>
            <select
              className="form-select"
              value={actionFilter}
              onChange={(e) => {
                setActionFilter(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Actions</option>
              <option value="LOGIN">LOGIN</option>
              <option value="LOGOUT">LOGOUT</option>
              <option value="USER_POINTS_ADJUST">USER_POINTS_ADJUST</option>
              <option value="QR_CODE_UPLOAD">QR_CODE_UPLOAD</option>
              <option value="QR_CODE_ACTIVATE">QR_CODE_ACTIVATE</option>
              <option value="SUBSCRIPTION_APPROVED">SUBSCRIPTION_APPROVED</option>
              <option value="SUBSCRIPTION_REJECTED">SUBSCRIPTION_REJECTED</option>
            </select>
            <button className="btn btn-outline btn-sm" onClick={loadLogs}>Refresh</button>
          </div>
        </div>

        {error && <div className="form-error" style={{ margin: '16px' }}>{error}</div>}

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action</th>
                <th>Target</th>
                <th>Details</th>
                <th>Admin ID</th>
                <th>IP Address</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: '32px' }}>Loading audit logs...</td></tr>
              ) : logs.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: '32px' }}>No audit logs found.</td></tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id}>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {new Date(log.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' })}
                    </td>
                    <td>
                      <span className="pill pill-neutral" style={{ fontWeight: 700 }}>
                        {log.action}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.8rem', color: '#64748b' }}>{log.target_type}</span>
                      {log.target_id && (
                        <div className="code-font" style={{ fontSize: '0.75rem' }}>{log.target_id.substring(0, 10)}...</div>
                      )}
                    </td>
                    <td>{log.details || '—'}</td>
                    <td className="code-font" style={{ fontSize: '0.78rem' }}>{log.admin_id.substring(0, 10)}...</td>
                    <td className="code-font" style={{ fontSize: '0.78rem', color: '#64748b' }}>{log.ip_address || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

import React, { useEffect, useState } from 'react'
import { api, PointLedgerEntry } from '../api'

export const PointsPage: React.FC = () => {
  const [entries, setEntries] = useState<PointLedgerEntry[]>([])
  const [total, setTotal] = useState(0)
  const [searchReason, setSearchReason] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadLedger = async () => {
    try {
      setLoading(true)
      const res = await api.getPointsLedger('', searchReason, page, 30)
      setEntries(res.entries)
      setTotal(res.total)
    } catch (err: any) {
      setError(err.message || 'Failed to load points ledger')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLedger()
  }, [page])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadLedger()
  }

  return (
    <div>
      <div className="section-card">
        <div className="section-header">
          <h3 className="section-title">Points Ledger ({total})</h3>
          <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px' }}>
            <input
              type="text"
              className="form-input"
              placeholder="Filter by reason (e.g. completion, adjust)..."
              value={searchReason}
              onChange={(e) => setSearchReason(e.target.value)}
              style={{ width: '320px' }}
            />
            <button type="submit" className="btn btn-primary btn-sm">Filter</button>
          </form>
        </div>

        {error && <div className="form-error" style={{ margin: '16px' }}>{error}</div>}

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Student</th>
                <th>Change</th>
                <th>Balance After</th>
                <th>Reason</th>
                <th>Ref ID</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: '32px' }}>Loading ledger entries...</td></tr>
              ) : entries.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: '32px' }}>No points ledger records found.</td></tr>
              ) : (
                entries.map((entry) => (
                  <tr key={entry.id}>
                    <td>
                      <div><strong>{entry.user_name}</strong></div>
                      <div style={{ fontSize: '0.78rem', color: '#64748b' }}>{entry.user_email}</div>
                    </td>
                    <td>
                      <span style={{
                        color: entry.amount >= 0 ? '#10b981' : '#ef4444',
                        fontWeight: 'bold',
                        fontSize: '1rem',
                      }}>
                        {entry.amount >= 0 ? `+${entry.amount}` : entry.amount}
                      </span>
                    </td>
                    <td><strong>{entry.balance_after} pts</strong></td>
                    <td>{entry.reason}</td>
                    <td className="code-font">{entry.reference_id ? entry.reference_id.substring(0, 10) : '—'}</td>
                    <td>{new Date(entry.created_at).toLocaleString()}</td>
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

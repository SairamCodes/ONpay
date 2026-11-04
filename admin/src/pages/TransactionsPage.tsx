import React, { useEffect, useState } from 'react'
import { api, ExchangeSummary } from '../api'

export const TransactionsPage: React.FC = () => {
  const [transactions, setTransactions] = useState<ExchangeSummary[]>([])
  const [total, setTotal] = useState(0)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadTransactions = async () => {
    try {
      setLoading(true)
      const res = await api.getTransactions(statusFilter, search, page, 25)
      setTransactions(res.transactions)
      setTotal(res.total)
    } catch (err: any) {
      setError(err.message || 'Failed to load transactions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTransactions()
  }, [page, statusFilter])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadTransactions()
  }

  return (
    <div>
      <div className="section-card">
        <div className="section-header">
          <h3 className="section-title">Transactions Ledger ({total})</h3>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <select
              className="form-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Statuses</option>
              <option value="COMPLETED">COMPLETED</option>
              <option value="MATCHED">MATCHED</option>
              <option value="SEEKER_CONFIRMED">SEEKER_CONFIRMED</option>
              <option value="PROVIDER_CONFIRMED">PROVIDER_CONFIRMED</option>
              <option value="CANCELLED">CANCELLED</option>
            </select>

            <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                className="form-input"
                placeholder="Search user email or name..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <button type="submit" className="btn btn-primary btn-sm">Search</button>
            </form>
          </div>
        </div>

        {error && <div className="form-error" style={{ margin: '16px' }}>{error}</div>}

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Exchange ID</th>
                <th>Amount</th>
                <th>Mode</th>
                <th>Seeker</th>
                <th>Provider</th>
                <th>Confirmations</th>
                <th>Status</th>
                <th>Initiated / Completed</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} style={{ textAlign: 'center', padding: '32px' }}>Loading transactions...</td></tr>
              ) : transactions.length === 0 ? (
                <tr><td colSpan={8} style={{ textAlign: 'center', padding: '32px' }}>No transactions found.</td></tr>
              ) : (
                transactions.map((tx) => (
                  <tr key={tx.id}>
                    <td className="code-font"><strong>{tx.id.substring(0, 8)}...</strong></td>
                    <td><strong>₹{tx.amount}</strong></td>
                    <td>
                      <span className="pill pill-neutral">{tx.mode}</span>
                    </td>
                    <td>
                      <div><strong>{tx.seeker_name}</strong></div>
                      <div style={{ fontSize: '0.78rem', color: '#64748b' }}>{tx.seeker_email}</div>
                    </td>
                    <td>
                      <div><strong>{tx.provider_name}</strong></div>
                      <div style={{ fontSize: '0.78rem', color: '#64748b' }}>{tx.provider_email}</div>
                    </td>
                    <td>
                      <div style={{ fontSize: '0.78rem' }}>
                        <span>Cash: {tx.seeker_cash_received ? '✓' : '✗'}</span> | <span>UPI: {tx.provider_upi_received ? '✓' : '✗'}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`pill ${tx.status === 'COMPLETED' ? 'pill-success' : tx.status === 'CANCELLED' ? 'pill-danger' : 'pill-warning'}`}>
                        {tx.status}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontSize: '0.8rem' }}>{new Date(tx.created_at).toLocaleDateString()}</div>
                      {tx.completed_at && (
                        <div style={{ fontSize: '0.74rem', color: '#10b981' }}>
                          Done: {new Date(tx.completed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      )}
                    </td>
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

import React, { useEffect, useState } from 'react'
import { api, UserSummary, ExchangeSummary, PointLedgerEntry } from '../api'

export const UsersPage: React.FC = () => {
  const [users, setUsers] = useState<UserSummary[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // User detail modal state
  const [selectedUser, setSelectedUser] = useState<UserSummary | null>(null)
  const [userDetailExchanges, setUserDetailExchanges] = useState<ExchangeSummary[]>([])
  const [userDetailLedger, setUserDetailLedger] = useState<PointLedgerEntry[]>([])
  const [detailLoading, setDetailLoading] = useState(false)

  // Points adjust modal state
  const [adjustTargetUser, setAdjustTargetUser] = useState<UserSummary | null>(null)
  const [adjustAmount, setAdjustAmount] = useState<number>(10)
  const [adjustReason, setAdjustReason] = useState<string>('Administrative incentive')
  const [adjustSubmitting, setAdjustSubmitting] = useState(false)

  const loadUsers = async () => {
    try {
      setLoading(true)
      const res = await api.getUsers(search, page, 25)
      setUsers(res.users)
      setTotal(res.total)
    } catch (err: any) {
      setError(err.message || 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
  }, [page])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadUsers()
  }

  const handleViewDetail = async (user: UserSummary) => {
    setSelectedUser(user)
    try {
      setDetailLoading(true)
      const res = await api.getUserDetail(user.id)
      setUserDetailExchanges(res.exchanges)
      setUserDetailLedger(res.ledger)
    } catch (err: any) {
      alert(err.message || 'Failed to load user details')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleAdjustPointsSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!adjustTargetUser) return
    try {
      setAdjustSubmitting(true)
      await api.adjustPoints(adjustTargetUser.id, adjustAmount, adjustReason.trim())
      alert(`Successfully adjusted ${adjustAmount > 0 ? '+' : ''}${adjustAmount} points for ${adjustTargetUser.name}`)
      setAdjustTargetUser(null)
      loadUsers()
      if (selectedUser && selectedUser.id === adjustTargetUser.id) {
        handleViewDetail(selectedUser)
      }
    } catch (err: any) {
      alert(err.message || 'Failed to adjust points')
    } finally {
      setAdjustSubmitting(false)
    }
  }

  return (
    <div>
      <div className="section-card">
        <div className="section-header">
          <div>
            <h3 className="section-title">Student Directory ({total})</h3>
          </div>
          <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px' }}>
            <input
              type="text"
              className="form-input"
              placeholder="Search name, email, phone, college..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: '280px' }}
            />
            <button type="submit" className="btn btn-primary btn-sm">Search</button>
            {search && (
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={() => {
                  setSearch('')
                  setPage(1)
                  setTimeout(loadUsers, 50)
                }}
              >
                Clear
              </button>
            )}
          </form>
        </div>

        {error && <div className="form-error" style={{ margin: '16px' }}>{error}</div>}

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Student</th>
                <th>Contact</th>
                <th>College</th>
                <th>Plan</th>
                <th>Points</th>
                <th>Last Login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: '32px' }}>Loading students...</td></tr>
              ) : users.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: '32px' }}>No students found matching your criteria.</td></tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <div><strong>{u.name}</strong></div>
                      <div className="code-font" style={{ fontSize: '0.78rem', color: '#64748b' }}>{u.id.substring(0, 8)}...</div>
                    </td>
                    <td>
                      <div>{u.email}</div>
                      <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{u.phone}</div>
                    </td>
                    <td>{u.college || '—'}</td>
                    <td>
                      <span className={`pill ${u.plan === 'pro' ? 'pill-pro' : u.plan === 'plus' ? 'pill-plus' : 'pill-neutral'}`}>
                        {u.plan.toUpperCase()}
                      </span>
                    </td>
                    <td>
                      <strong>{u.points} pts</strong>
                    </td>
                    <td>
                      {u.last_login_at ? (
                        <span style={{ fontSize: '0.82rem' }}>
                          {new Date(u.last_login_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                        </span>
                      ) : (
                        <span style={{ color: '#94a3b8', fontSize: '0.82rem' }}>Never</span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => handleViewDetail(u)}
                        >
                          Details
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => setAdjustTargetUser(u)}
                        >
                          ± Points
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* User Detail Modal */}
      {selectedUser && (
        <div className="modal-overlay" onClick={() => setSelectedUser(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '750px' }}>
            <div className="modal-header">
              <h3 className="modal-title">Student Profile: {selectedUser.name}</h3>
              <button className="modal-close" onClick={() => setSelectedUser(null)}>&times;</button>
            </div>
            <div className="modal-body">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
                <div><strong>Email:</strong> {selectedUser.email}</div>
                <div><strong>Phone:</strong> {selectedUser.phone}</div>
                <div><strong>College:</strong> {selectedUser.college || 'N/A'}</div>
                <div><strong>Current Plan:</strong> {selectedUser.plan.toUpperCase()}</div>
                <div><strong>Total Points:</strong> {selectedUser.points}</div>
                <div><strong>Last Login:</strong> {selectedUser.last_login_at ? new Date(selectedUser.last_login_at).toLocaleString() : 'Never'}</div>
              </div>

              <h4 style={{ marginBottom: '12px', fontSize: '1rem' }}>Recent Exchanges</h4>
              {detailLoading ? (
                <p>Loading exchanges...</p>
              ) : userDetailExchanges.length === 0 ? (
                <p style={{ color: '#64748b' }}>No exchanges recorded.</p>
              ) : (
                <div className="table-responsive" style={{ maxHeight: '200px', overflowY: 'auto', marginBottom: '20px' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Amount</th>
                        <th>Mode</th>
                        <th>Status</th>
                        <th>Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {userDetailExchanges.map((ex) => (
                        <tr key={ex.id}>
                          <td className="code-font">{ex.id.substring(0, 8)}</td>
                          <td>₹{ex.amount}</td>
                          <td>{ex.mode}</td>
                          <td>
                            <span className={`pill ${ex.status === 'COMPLETED' ? 'pill-success' : 'pill-neutral'}`}>
                              {ex.status}
                            </span>
                          </td>
                          <td>{new Date(ex.created_at).toLocaleDateString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <h4 style={{ marginBottom: '12px', fontSize: '1rem' }}>Points History</h4>
              {detailLoading ? (
                <p>Loading points ledger...</p>
              ) : userDetailLedger.length === 0 ? (
                <p style={{ color: '#64748b' }}>No point entries recorded.</p>
              ) : (
                <div className="table-responsive" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Change</th>
                        <th>Balance After</th>
                        <th>Reason</th>
                        <th>Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {userDetailLedger.map((lg) => (
                        <tr key={lg.id}>
                          <td style={{ color: lg.amount >= 0 ? '#10b981' : '#ef4444', fontWeight: 'bold' }}>
                            {lg.amount >= 0 ? `+${lg.amount}` : lg.amount}
                          </td>
                          <td>{lg.balance_after} pts</td>
                          <td>{lg.reason}</td>
                          <td>{new Date(lg.created_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button
                className="btn btn-primary"
                onClick={() => {
                  const target = selectedUser
                  setSelectedUser(null)
                  setAdjustTargetUser(target)
                }}
              >
                Adjust Points
              </button>
              <button className="btn btn-outline" onClick={() => setSelectedUser(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Adjust Points Modal */}
      {adjustTargetUser && (
        <div className="modal-overlay" onClick={() => setAdjustTargetUser(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">Adjust Points: {adjustTargetUser.name}</h3>
              <button className="modal-close" onClick={() => setAdjustTargetUser(null)}>&times;</button>
            </div>
            <form onSubmit={handleAdjustPointsSubmit}>
              <div className="modal-body">
                <p style={{ marginBottom: '16px', color: '#64748b' }}>
                  Current balance: <strong>{adjustTargetUser.points} points</strong>
                </p>
                <div className="form-group">
                  <label>Point Amount (positive to add, negative to deduct)</label>
                  <input
                    type="number"
                    className="form-input"
                    required
                    value={adjustAmount}
                    onChange={(e) => setAdjustAmount(parseInt(e.target.value) || 0)}
                  />
                </div>
                <div className="form-group">
                  <label>Audit Reason (required)</label>
                  <input
                    type="text"
                    className="form-input"
                    required
                    placeholder="e.g., Campus event reward / Manual correction"
                    value={adjustReason}
                    onChange={(e) => setAdjustReason(e.target.value)}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => setAdjustTargetUser(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={adjustSubmitting || adjustAmount === 0 || !adjustReason.trim()}
                >
                  {adjustSubmitting ? 'Applying...' : 'Confirm Adjustment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

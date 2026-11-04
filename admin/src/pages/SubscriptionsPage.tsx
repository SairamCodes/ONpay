import React, { useEffect, useState } from 'react'
import { api, SubscriptionRequestItem, getAdminToken, resolveAdminUrl } from '../api'

export const SubscriptionsPage: React.FC = () => {
  const [requests, setRequests] = useState<SubscriptionRequestItem[]>([])
  const [total, setTotal] = useState(0)
  const [statusFilter, setStatusFilter] = useState('PENDING')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Proof preview modal
  const [previewReq, setPreviewReq] = useState<SubscriptionRequestItem | null>(null)
  const [proofBlobUrl, setProofBlobUrl] = useState<string | null>(null)
  const [proofLoading, setProofLoading] = useState(false)

  // Rejection modal
  const [rejectingReq, setRejectingReq] = useState<SubscriptionRequestItem | null>(null)
  const [rejectReason, setRejectReason] = useState('Payment reference could not be verified on UPI bank statement.')
  const [submitting, setSubmitting] = useState(false)

  const loadRequests = async () => {
    try {
      setLoading(true)
      const res = await api.getSubscriptions(statusFilter, page, 25)
      setRequests(res.requests)
      setTotal(res.total)
    } catch (err: any) {
      setError(err.message || 'Failed to load subscription requests')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadRequests()
  }, [page, statusFilter])

  const openProofModal = async (req: SubscriptionRequestItem) => {
    setPreviewReq(req)
    setProofLoading(true)
    setProofBlobUrl(null)
    try {
      const token = getAdminToken()
      const headers: Record<string, string> = {}
      if (token) headers['Authorization'] = `Bearer ${token}`
      const proofUrl = resolveAdminUrl(`/api/admin/subscriptions/${req.id}/proof`)
      const res = await fetch(proofUrl, {
        headers,
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Failed to load proof image')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      setProofBlobUrl(url)
    } catch (err: any) {
      alert(err.message || 'Failed to load proof screenshot')
    } finally {
      setProofLoading(false)
    }
  }

  const closeProofModal = () => {
    if (proofBlobUrl) {
      URL.revokeObjectURL(proofBlobUrl)
    }
    setProofBlobUrl(null)
    setPreviewReq(null)
  }

  const handleApprove = async (req: SubscriptionRequestItem) => {
    const ok = window.confirm(`Approve payment of ₹${req.amount} (UTR: ${req.upi_ref}) and activate ${req.plan_name.toUpperCase()} for ${req.user_name}?`)
    if (!ok) return
    try {
      setSubmitting(true)
      await api.approveSubscription(req.id)
      alert(`Subscription successfully activated for ${req.user_name}!`)
      if (previewReq && previewReq.id === req.id) closeProofModal()
      loadRequests()
    } catch (err: any) {
      alert(err.message || 'Approval failed')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRejectSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!rejectingReq) return
    try {
      setSubmitting(true)
      await api.rejectSubscription(rejectingReq.id, rejectReason.trim())
      alert('Subscription request rejected.')
      setRejectingReq(null)
      if (previewReq && previewReq.id === rejectingReq.id) closeProofModal()
      loadRequests()
    } catch (err: any) {
      alert(err.message || 'Rejection failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <div className="section-card">
        <div className="section-header">
          <h3 className="section-title">Subscription Payment Reviews ({total})</h3>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <select
              className="form-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                setPage(1)
              }}
            >
              <option value="PENDING">Pending Review (Action Required)</option>
              <option value="APPROVED">Approved</option>
              <option value="REJECTED">Rejected</option>
              <option value="">All Statuses</option>
            </select>
            <button className="btn btn-outline btn-sm" onClick={loadRequests}>Refresh</button>
          </div>
        </div>

        {error && <div className="form-error" style={{ margin: '16px' }}>{error}</div>}

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Student</th>
                <th>Plan & Price</th>
                <th>UPI UTR / Ref</th>
                <th>Submitted</th>
                <th>Review Target (20m)</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: '32px' }}>Loading requests...</td></tr>
              ) : requests.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: '32px' }}>No subscription payment requests found.</td></tr>
              ) : (
                requests.map((req) => {
                  const elapsedMinutes = Math.floor(req.elapsed_seconds / 60)
                  return (
                    <tr key={req.id}>
                      <td>
                        <div><strong>{req.user_name}</strong></div>
                        <div style={{ fontSize: '0.78rem', color: '#64748b' }}>{req.user_email}</div>
                      </td>
                      <td>
                        <span className={`pill ${req.plan_name === 'pro' ? 'pill-pro' : 'pill-plus'}`}>
                          {req.plan_name.toUpperCase()}
                        </span>
                        <div style={{ marginTop: '4px', fontWeight: 'bold' }}>₹{req.amount}</div>
                      </td>
                      <td>
                        <div className="code-font" style={{ fontWeight: 600 }}>{req.upi_ref}</div>
                        {req.has_proof && (
                          <span style={{ fontSize: '0.75rem', color: '#10b981' }}>📷 Proof attached</span>
                        )}
                      </td>
                      <td>{new Date(req.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</td>
                      <td>
                        {req.status === 'PENDING' ? (
                          <div>
                            <span className={`pill ${req.is_overdue ? 'pill-danger' : 'pill-warning'}`}>
                              {elapsedMinutes}m elapsed
                            </span>
                            {req.is_overdue && (
                              <div style={{ fontSize: '0.72rem', color: '#ef4444', fontWeight: 600, marginTop: '2px' }}>
                                ⚠️ Target exceeded (&gt;20m)
                              </div>
                            )}
                          </div>
                        ) : (
                          <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                            {req.reviewed_at ? new Date(req.reviewed_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : '—'}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className={`pill ${req.status === 'APPROVED' ? 'pill-success' : req.status === 'REJECTED' ? 'pill-danger' : 'pill-warning'}`}>
                          {req.status}
                        </span>
                        {req.rejection_reason && (
                          <div style={{ fontSize: '0.75rem', color: '#991b1b', maxWidth: '160px', marginTop: '2px' }}>
                            {req.rejection_reason}
                          </div>
                        )}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          {req.has_proof && (
                            <button
                              className="btn btn-outline btn-sm"
                              onClick={() => openProofModal(req)}
                            >
                              Proof
                            </button>
                          )}
                          {req.status === 'PENDING' && (
                            <>
                              <button
                                className="btn btn-success btn-sm"
                                disabled={submitting}
                                onClick={() => handleApprove(req)}
                              >
                                Approve
                              </button>
                              <button
                                className="btn btn-danger btn-sm"
                                disabled={submitting}
                                onClick={() => setRejectingReq(req)}
                              >
                                Reject
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Proof Preview Modal */}
      {previewReq && (
        <div className="modal-overlay" onClick={closeProofModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '640px' }}>
            <div className="modal-header">
              <h3 className="modal-title">Payment Screenshot: {previewReq.user_name}</h3>
              <button className="modal-close" onClick={closeProofModal}>&times;</button>
            </div>
            <div className="modal-body" style={{ textAlign: 'center' }}>
              <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-around', backgroundColor: '#f8fafc', padding: '12px', borderRadius: '8px' }}>
                <div><strong>Plan:</strong> {previewReq.plan_name.toUpperCase()}</div>
                <div><strong>Amount:</strong> ₹{previewReq.amount}</div>
                <div><strong>UTR / Ref:</strong> <span className="code-font">{previewReq.upi_ref}</span></div>
              </div>

              {proofLoading ? (
                <div style={{ padding: '40px' }}>Loading secure screenshot...</div>
              ) : proofBlobUrl ? (
                <img
                  src={proofBlobUrl}
                  alt="Payment proof screenshot"
                  style={{
                    maxWidth: '100%',
                    maxHeight: '480px',
                    borderRadius: '8px',
                    boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
                    objectFit: 'contain',
                  }}
                />
              ) : (
                <div style={{ color: '#ef4444' }}>Unable to load proof image.</div>
              )}
            </div>
            <div className="modal-footer">
              {previewReq.status === 'PENDING' && (
                <>
                  <button
                    className="btn btn-success"
                    disabled={submitting}
                    onClick={() => handleApprove(previewReq)}
                  >
                    Approve Payment
                  </button>
                  <button
                    className="btn btn-danger"
                    disabled={submitting}
                    onClick={() => setRejectingReq(previewReq)}
                  >
                    Reject
                  </button>
                </>
              )}
              <button className="btn btn-outline" onClick={closeProofModal}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Rejection Modal */}
      {rejectingReq && (
        <div className="modal-overlay" onClick={() => setRejectingReq(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">Reject Payment Request: {rejectingReq.user_name}</h3>
              <button className="modal-close" onClick={() => setRejectingReq(null)}>&times;</button>
            </div>
            <form onSubmit={handleRejectSubmit}>
              <div className="modal-body">
                <p style={{ marginBottom: '16px', color: '#64748b' }}>
                  Please provide a clear reason for rejecting payment reference <strong>{rejectingReq.upi_ref}</strong>. The student will be notified.
                </p>
                <div className="form-group">
                  <label>Rejection Reason</label>
                  <textarea
                    className="form-input"
                    rows={4}
                    required
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => setRejectingReq(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-danger"
                  disabled={submitting || !rejectReason.trim()}
                >
                  {submitting ? 'Rejecting...' : 'Confirm Rejection'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

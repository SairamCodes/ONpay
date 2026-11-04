import React, { useEffect, useState } from 'react'
import { api, QRCodeItem, resolveAdminUrl } from '../api'

export const QRCodePage: React.FC = () => {
  const [qrCodes, setQrCodes] = useState<QRCodeItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Upload state
  const [file, setFile] = useState<File | null>(null)
  const [upiId, setUpiId] = useState('')
  const [uploading, setUploading] = useState(false)

  const loadQRs = async () => {
    try {
      setLoading(true)
      const res = await api.getQRCodes()
      setQrCodes(res.qr_codes)
    } catch (err: any) {
      setError(err.message || 'Failed to load QR codes')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadQRs()
  }, [])

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file || !upiId.trim()) {
      alert('Please select a QR image and enter a valid UPI ID (e.g. name@okhdfcbank)')
      return
    }
    try {
      setUploading(true)
      await api.uploadQRCode(file, upiId.trim())
      alert('QR Code uploaded and set as active receiving QR!')
      setFile(null)
      setUpiId('')
      loadQRs()
    } catch (err: any) {
      alert(err.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleActivate = async (qrId: string) => {
    try {
      await api.activateQRCode(qrId)
      alert('Selected QR Code activated for all student checkouts.')
      loadQRs()
    } catch (err: any) {
      alert(err.message || 'Failed to activate QR Code')
    }
  }

  const activeQR = qrCodes.find((q) => q.is_active)

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(300px, 1fr) 2fr', gap: '24px', alignItems: 'start' }}>
        {/* Upload Form Card */}
        <div className="section-card">
          <div className="section-header">
            <h3 className="section-title">Upload New Receiving QR</h3>
          </div>
          <form onSubmit={handleUploadSubmit} style={{ padding: '24px' }}>
            <div className="form-group">
              <label>UPI ID / VPA Handle</label>
              <input
                type="text"
                className="form-input"
                required
                placeholder="e.g. onpay@okhdfcbank"
                value={upiId}
                onChange={(e) => setUpiId(e.target.value)}
              />
              <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                Students will send payments to this UPI address.
              </span>
            </div>

            <div className="form-group">
              <label>QR Code Image (.png, .jpg, .webp)</label>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                required
                className="form-input"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    setFile(e.target.files[0])
                  }
                }}
              />
              <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                High-contrast image without borders, max 5 MB.
              </span>
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-full"
              disabled={uploading || !file || !upiId.trim()}
              style={{ marginTop: '12px' }}
            >
              {uploading ? 'Uploading & Activating...' : 'Upload & Set Active'}
            </button>
          </form>
        </div>

        {/* Current Active QR Display & History */}
        <div>
          {activeQR && (
            <div className="section-card" style={{ borderColor: '#10b981', marginBottom: '24px' }}>
              <div className="section-header" style={{ backgroundColor: '#ecfdf5' }}>
                <h3 className="section-title" style={{ color: '#065f46' }}>
                  ✓ Currently Active Receiving QR
                </h3>
                <span className="pill pill-success">LIVE IN CHECKOUT</span>
              </div>
              <div style={{ padding: '24px', display: 'flex', gap: '24px', alignItems: 'center' }}>
                <img
                  src={resolveAdminUrl(activeQR.image_url)}
                  alt="Active QR Code"
                  style={{ width: '160px', height: '160px', border: '1px solid #e2e8f0', borderRadius: '8px', objectFit: 'contain' }}
                />
                <div>
                  <div style={{ fontSize: '0.85rem', color: '#64748b' }}>Active UPI ID:</div>
                  <div className="code-font" style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#0f172a', marginBottom: '8px' }}>
                    {activeQR.upi_id}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#64748b' }}>
                    Activated: {new Date(activeQR.created_at).toLocaleString()}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="section-card">
            <div className="section-header">
              <h3 className="section-title">QR Code Library ({qrCodes.length})</h3>
            </div>
            {error && <div className="form-error" style={{ margin: '16px' }}>{error}</div>}
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>QR Preview</th>
                    <th>UPI ID</th>
                    <th>Status</th>
                    <th>Upload Date</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={5} style={{ textAlign: 'center', padding: '24px' }}>Loading QR codes...</td></tr>
                  ) : qrCodes.length === 0 ? (
                    <tr><td colSpan={5} style={{ textAlign: 'center', padding: '24px' }}>No QR codes uploaded yet.</td></tr>
                  ) : (
                    qrCodes.map((qr) => (
                      <tr key={qr.id}>
                        <td>
                          <img
                            src={resolveAdminUrl(qr.image_url)}
                            alt="QR Thumbnail"
                            style={{ width: '48px', height: '48px', borderRadius: '4px', objectFit: 'contain' }}
                          />
                        </td>
                        <td className="code-font"><strong>{qr.upi_id}</strong></td>
                        <td>
                          <span className={`pill ${qr.is_active ? 'pill-success' : 'pill-neutral'}`}>
                            {qr.is_active ? 'ACTIVE' : 'INACTIVE'}
                          </span>
                        </td>
                        <td>{new Date(qr.created_at).toLocaleDateString()}</td>
                        <td>
                          {!qr.is_active && (
                            <button
                              className="btn btn-outline btn-sm"
                              onClick={() => handleActivate(qr.id)}
                            >
                              Make Active
                            </button>
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
      </div>
    </div>
  )
}

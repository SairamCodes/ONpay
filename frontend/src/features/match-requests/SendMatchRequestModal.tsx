import { useState, type FormEvent } from 'react'
import type { Listing } from '../../types'
import { money } from '../../utils'
import { api, json } from '../../api'
import { Avatar } from '../../components/Avatar'
import { Icon } from '../../components/Icon'

interface SendMatchRequestModalProps {
  listing: Listing
  onClose: () => void
  onSuccess: () => void
}

export function SendMatchRequestModal({
  listing,
  onClose,
  onSuccess,
}: SendMatchRequestModalProps) {
  const [amountRupees, setAmountRupees] = useState(
    String(Math.floor(listing.amount_min / 100))
  )
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const ownerName = listing.owner?.full_name || listing.owner_name || 'Student'
  const minRupees = Math.floor(listing.amount_min / 100)
  const maxRupees = Math.floor(listing.amount_max / 100)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    const num = Number(amountRupees)
    if (!num || num <= 0) {
      setError('Please enter a valid amount.')
      return
    }
    const amountPaise = Math.round(num * 100)
    if (amountPaise < listing.amount_min || amountPaise > listing.amount_max) {
      setError(`Amount must be between ₹${minRupees} and ₹${maxRupees}.`)
      return
    }

    setBusy(true)
    try {
      await api(
        '/api/match-requests',
        json({
          provider_listing_id: listing.id,
          listing_id: listing.id,
          amount: amountPaise,
          note: note.trim(),
        })
      )
      setSuccess(true)
      setTimeout(() => {
        onSuccess()
      }, 1000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send match request')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <section className="bottom-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-handle" />
        <h2>Send Match Request</h2>
        <p>Coordinate cash exchange directly with this student.</p>

        <div className="payee-summary">
          <Avatar name={ownerName} size="md" />
          <span>
            <strong>{ownerName}</strong>
            <small>
              {listing.location}
              {listing.distance_km != null ? ` · ${listing.distance_km} km away` : ''}
            </small>
          </span>
          <b>
            {money(listing.amount_min)}
            {listing.amount_max !== listing.amount_min ? `–${money(listing.amount_max)}` : ''}
          </b>
        </div>

        {success ? (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <div
              style={{
                width: 50,
                height: 50,
                borderRadius: '50%',
                background: '#d1f5e0',
                color: 'var(--green)',
                display: 'grid',
                placeItems: 'center',
                margin: '0 auto 12px',
              }}
            >
              <Icon name="check" size={26} />
            </div>
            <strong style={{ fontSize: 16, color: 'var(--navy)' }}>Request Sent!</strong>
            <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>
              We'll notify you when {ownerName} responds.
            </p>
          </div>
        ) : (
          <form className="stack-form" onSubmit={handleSubmit}>
            <label>
              Exchange Amount
              <div className="money-input">
                <span>₹</span>
                <input
                  type="number"
                  required
                  min={minRupees}
                  max={maxRupees}
                  step="1"
                  value={amountRupees}
                  onChange={(e) => setAmountRupees(e.target.value)}
                  placeholder="500"
                />
              </div>
              <small className="field-hint">
                Offered range: ₹{minRupees}
                {maxRupees !== minRupees ? ` to ₹${maxRupees}` : ''}
              </small>
            </label>

            <label>
              Message or Note <span className="optional">(optional)</span>
              <textarea
                maxLength={300}
                rows={2}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. Can meet near campus cafe in 15 mins"
              />
            </label>

            {error && <p className="inline-error">{error}</p>}

            <button className="button button-primary button-wide" disabled={busy}>
              {busy ? 'Sending Request…' : 'Send Match Request'}{' '}
              <Icon name="arrow" size={16} />
            </button>
            <button type="button" className="sheet-cancel" onClick={onClose} disabled={busy}>
              Cancel
            </button>
          </form>
        )}
      </section>
    </div>
  )
}

export default SendMatchRequestModal

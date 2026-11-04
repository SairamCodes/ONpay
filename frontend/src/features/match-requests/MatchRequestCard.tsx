import { useState } from 'react'
import type { MatchRequest, Exchange } from '../../types'
import { money } from '../../utils'
import { Avatar } from '../../components/Avatar'
import { api, json } from '../../api'

interface MatchRequestCardProps {
  request: MatchRequest
  currentUserId: string
  onUpdate?: () => void
  onSelectExchange?: (exchange: Exchange) => void
}

export function MatchRequestCard({
  request,
  currentUserId,
  onUpdate,
  onSelectExchange,
}: MatchRequestCardProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const isIncoming = currentUserId === request.provider_id
  const otherName = isIncoming
    ? request.seeker_name || request.seeker_listing?.owner?.full_name || request.seeker_listing?.owner_name || 'Seeker'
    : request.provider_name || request.provider_listing?.owner?.full_name || request.provider_listing?.owner_name || 'Provider'

  const distance = request.seeker_listing?.distance_km ?? request.provider_listing?.distance_km

  const handleAccept = async () => {
    setBusy(true)
    setError('')
    try {
      const res = await api<{ exchange?: Exchange; match_request?: MatchRequest }>(
        `/api/match-requests/${request.id}/accept`,
        { method: 'POST' }
      )
      if (res.exchange && onSelectExchange) {
        onSelectExchange(res.exchange)
      } else {
        onUpdate?.()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not accept request')
    } finally {
      setBusy(false)
    }
  }

  const handleReject = async () => {
    setBusy(true)
    setError('')
    try {
      await api(`/api/match-requests/${request.id}/reject`, { method: 'POST' })
      onUpdate?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reject request')
    } finally {
      setBusy(false)
    }
  }

  const handleCancel = async () => {
    setBusy(true)
    setError('')
    try {
      await api(`/api/match-requests/${request.id}/cancel`, { method: 'POST' })
      onUpdate?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not cancel request')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="match-request-card">
      <div className="mr-header">
        <Avatar name={otherName} size="md" />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <strong style={{ fontSize: 13, color: 'var(--navy)' }}>{otherName}</strong>
            <span className={`mr-status ${request.status}`}>{request.status}</span>
          </div>
          <div style={{ display: 'flex', gap: 8, fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
            <span className="mr-amount">{money(request.amount)}</span>
            {distance != null && <span>· {distance} km away</span>}
            <span>· {new Date(request.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</span>
          </div>
        </div>
      </div>

      {request.note && (
        <p style={{ margin: '0 0 10px', fontSize: 12, color: 'var(--muted)', fontStyle: 'italic' }}>
          "{request.note}"
        </p>
      )}

      {error && <p className="inline-error" style={{ margin: '6px 0' }}>{error}</p>}

      {request.status === 'pending' && (
        <div className="mr-actions">
          {isIncoming ? (
            <>
              <button className="accept-btn" disabled={busy} onClick={handleAccept}>
                {busy ? 'Accepting…' : 'Accept Request'}
              </button>
              <button className="reject-btn" disabled={busy} onClick={handleReject}>
                {busy ? 'Rejecting…' : 'Decline'}
              </button>
            </>
          ) : (
            <button className="cancel-btn" disabled={busy} onClick={handleCancel}>
              {busy ? 'Cancelling…' : 'Cancel Request'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default MatchRequestCard

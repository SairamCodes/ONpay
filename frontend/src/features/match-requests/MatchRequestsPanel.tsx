import { useCallback, useEffect, useState } from 'react'
import type { MatchRequest, Exchange } from '../../types'
import { api } from '../../api'
import { useAuth } from '../../contexts/AuthContext'
import { useWebSocket } from '../../contexts/WebSocketContext'
import { MatchRequestCard } from './MatchRequestCard'
import { EmptyState } from '../../components/EmptyState'

interface MatchRequestsPanelProps {
  onSelectExchange?: (exchange: Exchange) => void
  navigate?: (screen: any) => void
}

export function MatchRequestsPanel({ onSelectExchange, navigate }: MatchRequestsPanelProps) {
  const { user } = useAuth()
  const { ws } = useWebSocket()
  const [incoming, setIncoming] = useState<MatchRequest[]>([])
  const [outgoing, setOutgoing] = useState<MatchRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadRequests = useCallback(async () => {
    if (!user) return
    setLoading(true)
    setError('')
    try {
      const data = await api<any>('/api/match-requests')
      if (Array.isArray(data.incoming) && Array.isArray(data.outgoing)) {
        setIncoming(data.incoming)
        setOutgoing(data.outgoing)
      } else if (Array.isArray(data.match_requests)) {
        setIncoming(data.match_requests.filter((r: MatchRequest) => r.provider_id === user.id))
        setOutgoing(data.match_requests.filter((r: MatchRequest) => r.seeker_id === user.id))
      } else if (Array.isArray(data)) {
        setIncoming(data.filter((r: MatchRequest) => r.provider_id === user.id))
        setOutgoing(data.filter((r: MatchRequest) => r.seeker_id === user.id))
      } else {
        setIncoming([])
        setOutgoing([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load match requests')
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    void loadRequests()
  }, [loadRequests])

  useEffect(() => {
    if (!ws) return
    const handleWsEvent = () => {
      void loadRequests()
    }
    ws.on('match_request_received', handleWsEvent)
    ws.on('match_request_updated', handleWsEvent)
    return () => {
      ws.off('match_request_received', handleWsEvent)
      ws.off('match_request_updated', handleWsEvent)
    }
  }, [ws, loadRequests])

  if (!user) return null

  const hasRequests = incoming.length > 0 || outgoing.length > 0

  return (
    <div className="match-requests-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h2>Match Requests</h2>
        <button
          className="text-action"
          onClick={() => void loadRequests()}
          disabled={loading}
          style={{ fontSize: 11 }}
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="inline-error" style={{ marginBottom: 12 }}>{error}</p>}

      {loading && !hasRequests ? (
        <div className="loading-inline">
          <span className="spinner" /> Loading match requests…
        </div>
      ) : !hasRequests ? (
        <EmptyState
          icon="search"
          title="No Match Requests"
          body="When students send you a match request or when you request a match, they will appear here."
          action={
            navigate ? (
              <button className="button button-soft" onClick={() => navigate('matches')}>
                Browse listings
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          {incoming.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
                Incoming Requests ({incoming.length})
              </h3>
              {incoming.map((req) => (
                <MatchRequestCard
                  key={req.id}
                  request={req}
                  currentUserId={user.id}
                  onUpdate={loadRequests}
                  onSelectExchange={onSelectExchange}
                />
              ))}
            </div>
          )}

          {outgoing.length > 0 && (
            <div>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
                Outgoing Requests ({outgoing.length})
              </h3>
              {outgoing.map((req) => (
                <MatchRequestCard
                  key={req.id}
                  request={req}
                  currentUserId={user.id}
                  onUpdate={loadRequests}
                  onSelectExchange={onSelectExchange}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default MatchRequestsPanel

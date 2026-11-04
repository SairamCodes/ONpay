import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import type { User } from '../types'
import { money } from '../utils'
import { api, json } from '../api'
import { useWebSocket } from '../contexts/WebSocketContext'
import { PageTitle } from '../components/PageTitle'
import { Avatar } from '../components/Avatar'
import { Icon } from '../components/Icon'
import { EmptyState } from '../components/EmptyState'

export function ChatsPage({
  targetUserId,
  user,
  setChatTarget,
  setError,
}: {
  targetUserId: string | null
  user: User
  setChatTarget: (id: string | null) => void
  setError: (message: string) => void
}) {
  const { ws } = useWebSocket()
  const [chats, setChats] = useState<any[]>([])
  const [friends, setFriends] = useState<any[]>([])
  const [showFriends, setShowFriends] = useState(false)
  const [active, setActive] = useState<any>(null)
  const [friendState, setFriendState] = useState<{ status: string; request_id: string | null }>({ status: 'none', request_id: null })
  const [messages, setMessages] = useState<any[]>([])
  const [body, setBody] = useState('')
  const [loading, setLoading] = useState(true)
  const [actionsOpen, setActionsOpen] = useState(false)
  const messagesEnd = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api('/api/chats')
      setChats(data.chats)
      if (targetUserId) {
        const conversation = await api(`/api/chats/with/${targetUserId}`)
        setActive(conversation)
        setMessages(conversation.messages)
        const fStatus = await api(`/api/friends/status/${targetUserId}`)
        setFriendState(fStatus)
      } else {
        setActive(null)
        setMessages([])
        setFriendState({ status: 'none', request_id: null })
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not load chats')
    } finally {
      setLoading(false)
    }
  }, [targetUserId, setError])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (showFriends) {
      api('/api/friends')
        .then((data) => setFriends(data.friends))
        .catch((failure) => setError(failure instanceof Error ? failure.message : 'Could not load friends'))
    }
  }, [showFriends, setError])

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // WebSocket subscription for chat messages
  useEffect(() => {
    if (!ws) return
    const handleWsMessage = (data: any) => {
      const newMsg = data?.message || data
      if (active) {
        if (
          (data?.conversation_id && active?.id === data.conversation_id) ||
          newMsg?.sender_id === active?.other_user?.id
        ) {
          setMessages((previous) => [...previous, newMsg])
        }
      }
      // Always refresh chats list
      api('/api/chats')
        .then((data) => setChats(data.chats))
        .catch(() => {})
    }

    ws.on('chat_message', handleWsMessage)
    return () => {
      ws.off('chat_message', handleWsMessage)
    }
  }, [ws, active])

  const selectChat = async (chat: any) => {
    setChatTarget(chat.other_user.id)
    setActive(chat)
    try {
      const detail = await api(`/api/chats/${chat.id}`)
      setMessages(detail.messages)
      const fStatus = await api(`/api/friends/status/${chat.other_user.id}`)
      setFriendState(fStatus)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not open chat')
    }
  }

  const selectFriend = async (friend: any) => {
    setChatTarget(friend.id)
    setShowFriends(false)
    try {
      const detail = await api(`/api/chats/with/${friend.id}`)
      setActive(detail)
      setMessages(detail.messages)
      const fStatus = await api(`/api/friends/status/${friend.id}`)
      setFriendState(fStatus)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not open chat')
    }
  }

  const sendFriendReq = async () => {
    const otherId = active?.other_user?.id
    if (!otherId) return
    try {
      const res = await api(`/api/friends/request/${otherId}${active.exchange_id ? `?exchange_id=${active.exchange_id}` : ''}`, json({}))
      setFriendState({ status: 'request_sent', request_id: res.request_id })
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not send friend request')
    }
  }

  const acceptFriend = async () => {
    if (!friendState.request_id) return
    try {
      await api(`/api/friends/requests/${friendState.request_id}/accept`, json({}))
      setFriendState({ status: 'friends', request_id: null })
      const data = await api('/api/friends')
      setFriends(data.friends)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not accept friend request')
    }
  }

  const rejectFriend = async () => {
    if (!friendState.request_id) return
    try {
      await api(`/api/friends/requests/${friendState.request_id}/reject`, json({}))
      setFriendState({ status: 'none', request_id: null })
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not decline friend request')
    }
  }

  const moderate = async (action: 'report' | 'block') => {
    const otherId = active?.other_user?.id
    if (!otherId) return
    try {
      if (action === 'report') {
        await api('/api/reports', json({ user_id: otherId, category: 'chat_report', details: '' }))
        setError('Your report was sent for review.')
      } else {
        await api('/api/blocks', json({ user_id: otherId }))
        setError('Student blocked. Their listings and messages are hidden from you.')
        setActive(null)
        setChatTarget(null)
        setMessages([])
        await load()
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : `Could not ${action} this student`)
    }
    setActionsOpen(false)
  }

  const send = async (event: FormEvent) => {
    event.preventDefault()
    if (!body.trim() || !active?.other_user?.id) return
    try {
      const result = await api(
        `/api/chats/with/${active.other_user.id}/messages${
          active.exchange_id ? `?exchange_id=${active.exchange_id}` : ''
        }`,
        json({ body })
      )
      setMessages((previous) => [...previous, result.message])
      setBody('')
      setActive((previous: any) => ({ ...previous, id: result.chat_id }))
      const data = await api('/api/chats')
      setChats(data.chats)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not send message')
    }
  }

  if (active) {
    return (
      <div className="chat-screen">
        <div className="chat-top">
          <button
            className="icon-button"
            onClick={() => {
              setChatTarget(null)
              setActive(null)
              setActionsOpen(false)
            }}
          >
            <Icon name="back" />
          </button>
          <Avatar name={active.other_user?.full_name || 'Student'} size="sm" />
          <span>
            <strong>{active.other_user?.full_name || 'Student'}</strong>
            <small>{active.exchange_id ? 'Exchange chat' : active.other_user?.college || 'ONPay chat'}</small>
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
            {friendState.status === 'friends' && <span className="friend-badge positive">✓ Friends</span>}
            {friendState.status === 'request_sent' && <span className="friend-badge neutral">Request Sent</span>}
            {friendState.status === 'request_received' && (
              <div className="friend-inline-actions">
                <button className="friend-action-btn accept" onClick={acceptFriend}>Accept</button>
                <button className="friend-action-btn reject" onClick={rejectFriend}>Decline</button>
              </div>
            )}
            {friendState.status === 'none' && (
              <button className="friend-action-btn add" onClick={sendFriendReq}>+ Add Friend</button>
            )}
            <button
              className="more-button"
              aria-label="Chat safety actions"
              onClick={() => setActionsOpen((open) => !open)}
            >
              •••
            </button>
          </div>
        </div>

        {/* Exchange info banner */}
        {active.exchange_id && (
          <div
            style={{
              background: '#eef4ff',
              padding: '8px 16px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: 11,
              borderBottom: '1px solid #dfe9f7',
            }}
          >
            <span>
              <strong style={{ color: 'var(--navy)' }}>Exchange Reference</strong>
              {active.exchange?.status && (
                <span className="status-pill neutral" style={{ marginLeft: 6 }}>
                  {active.exchange.status.replaceAll('_', ' ')}
                </span>
              )}
            </span>
            {active.exchange?.amount && (
              <b style={{ color: 'var(--navy)' }}>{money(active.exchange.amount)}</b>
            )}
          </div>
        )}

        {actionsOpen && (
          <div className="chat-safety-actions">
            <button onClick={() => moderate('report')}>Report student</button>
            <button onClick={() => moderate('block')}>Block student</button>
          </div>
        )}

        <div className="chat-messages">
          {messages.length ? (
            messages.map((message: any) => (
              <div
                key={message.id}
                className={`message-bubble ${message.sender_id === user.id ? 'mine' : ''}`}
              >
                {message.body}
                <small>
                  {new Date(message.created_at).toLocaleTimeString([], {
                    hour: 'numeric',
                    minute: '2-digit',
                  })}
                </small>
              </div>
            ))
          ) : (
            <EmptyState
              icon="chat"
              title="Start a conversation"
              body="Keep exchange arrangements in ONPay chat. Never share your UPI PIN."
            />
          )}
          <div ref={messagesEnd} />
        </div>

        <form className="chat-composer" onSubmit={send}>
          <input
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={2000}
            placeholder="Type a message…"
          />
          <button className="send-button" disabled={!body.trim()} aria-label="Send message">
            <Icon name="arrow" />
          </button>
        </form>
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageTitle title="Chats" subtitle="Coordinate an exchange before meeting." />
      <div className="segmented small-tabs">
        <button className={!showFriends ? 'selected' : ''} onClick={() => setShowFriends(false)}>
          Conversations
        </button>
        <button className={showFriends ? 'selected' : ''} onClick={() => setShowFriends(true)}>
          Friends
        </button>
      </div>
      {loading ? (
        <div className="loading-inline">
          <span className="spinner" />Loading {showFriends ? 'friends' : 'chats'}…
        </div>
      ) : showFriends ? (
        friends.length ? (
          <div className="chat-list">
            {friends.map((friend) => (
              <button className="chat-row" key={friend.id} onClick={() => selectFriend(friend)}>
                <Avatar name={friend.full_name} />
                <span>
                  <strong>{friend.full_name}</strong>
                  <small>{friend.college || 'Verified exchange friend'}</small>
                </span>
                <small className="chat-date">Message</small>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState
            icon="user"
            title="No friends yet"
            body="Students are added after an exchange has been independently verified."
          />
        )
      ) : chats.length ? (
        <div className="chat-list">
          {chats.map((chat) => (
            <button className="chat-row" key={chat.id} onClick={() => selectChat(chat)}>
              <Avatar name={chat.other_user?.full_name || 'Student'} />
              <span>
                <strong>{chat.other_user?.full_name || 'Student'}</strong>
                <small>{chat.last_message}</small>
              </span>
              <small className="chat-date">{new Date(chat.updated_at).toLocaleDateString()}</small>
            </button>
          ))}
        </div>
      ) : (
        <EmptyState
          icon="chat"
          title="No conversations yet"
          body="Open a student listing to start a chat. Your messages are visible only to the participants."
        />
      )}
    </div>
  )
}

export default ChatsPage

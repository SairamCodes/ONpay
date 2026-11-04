import { resolveApiBase } from './api-config.js'

type EventHandler = (data: any) => void

export class ONPayWebSocket {
  private ws: WebSocket | null = null
  private listeners: Map<string, Set<EventHandler>> = new Map()
  private reconnectAttempt = 0
  private maxReconnectDelay = 30000
  private reconnectTimer: number | null = null
  private intentionallyClosed = false
  public connected = false

  connect() {
    this.intentionallyClosed = false
    const base = resolveApiBase(
      (import.meta as any).env?.VITE_API_BASE_URL,
      (import.meta as any).env?.DEV,
      window.location.hostname
    )
    const wsBase = base.replace(/^http/, 'ws') || `ws://${window.location.hostname}:8000`
    const url = `${wsBase}/api/ws`

    try {
      this.ws = new WebSocket(url)
      this.ws.onopen = () => {
        this.connected = true
        this.reconnectAttempt = 0
        this.emit('_status', { connected: true })
      }
      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type) this.emit(data.type, data.payload)
        } catch {}
      }
      this.ws.onclose = () => {
        this.connected = false
        this.emit('_status', { connected: false })
        if (!this.intentionallyClosed) this.scheduleReconnect()
      }
      this.ws.onerror = () => {
        this.ws?.close()
      }
    } catch {
      this.scheduleReconnect()
    }
  }

  disconnect() {
    this.intentionallyClosed = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this.ws = null
    this.connected = false
  }

  private scheduleReconnect() {
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempt), this.maxReconnectDelay)
    this.reconnectAttempt++
    this.reconnectTimer = window.setTimeout(() => this.connect(), delay)
  }

  on(event: string, handler: EventHandler) {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set())
    this.listeners.get(event)!.add(handler)
  }

  off(event: string, handler: EventHandler) {
    this.listeners.get(event)?.delete(handler)
  }

  private emit(event: string, data: any) {
    this.listeners.get(event)?.forEach((h) => h(data))
  }
}

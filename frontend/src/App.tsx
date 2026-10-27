import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { BrowserQRCodeReader as BrowserQRCodeReaderType, IScannerControls } from '@zxing/browser'
import { api, ApiError, json, patch } from './api'
import { getAuthState, restoreAuthSession } from './auth-session.js'
import { detectCurrentLocation, saveManualLocation } from './location.js'
import type { ResolvedLocation } from './location.js'
import { parseUpiPayload } from './upi.js'

type Screen = 'welcome' | 'signup' | 'login' | 'verify' | 'home' | 'matches' | 'need' | 'have' | 'chats' | 'scan' | 'transactions' | 'profile' | 'meetup' | 'student' | 'notifications' | 'subscriptions' | 'points' | 'location' | 'help' | 'payment'
type User = { id: string; full_name: string; email?: string | null; phone?: string | null; college?: string | null; location_label?: string | null; verified_email: boolean; verified_phone: boolean; plan: string; points: number; completed_exchanges: number; friends_count: number }
type OtpChannel = 'mobile' | 'email'
type OtpRequestResult = { accepted: true; challenge_id: string; expires_in_seconds: number; resend_in_seconds: number; channel: OtpChannel; contact: string; intent: 'signup' | 'login'; full_name?: string; college?: string | null; development_code?: string }
type Listing = { id: string; kind: 'need' | 'have'; amount_min: number; amount_max: number; location: string; availability: string; note: string; status: string; distance_km?: number | null; owner: { id: string; full_name: string; college?: string | null; verified: boolean }; mine?: boolean }
type Exchange = { id: string; amount: number; location: string; meetup_at: string; status: string; requester_id: string; provider_id: string; created_at?: string; requester_arrived: boolean; provider_arrived: boolean; requester_cash_confirmed: boolean; provider_cash_confirmed: boolean; other_user: { id: string; full_name: string; college?: string | null } }
type Payment = { id: string; reference: string; amount: number; status: string; upi_uri: string; verification_note: string }
type Coordinates = { latitude: number; longitude: number }
type GeoStatus = 'checking' | 'prompt' | 'loading' | 'ready' | 'denied' | 'unavailable' | 'error' | 'insecure'

const money = (paise: number) => `₹${Math.floor(paise / 100).toLocaleString('en-IN')}${paise % 100 ? `.${String(paise % 100).padStart(2, '0')}` : ''}`
const initials = (name = '') => name.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word[0]).join('').toUpperCase() || 'S'

function isAcceptedOtpRequest(value: unknown, channel: OtpChannel, intent: 'signup' | 'login'): value is OtpRequestResult {
  if (!value || typeof value !== 'object') return false
  const result = value as Record<string, unknown>
  return result.accepted === true
    && typeof result.challenge_id === 'string'
    && result.challenge_id.length > 0
    && typeof result.expires_in_seconds === 'number'
    && Number.isFinite(result.expires_in_seconds)
    && typeof result.resend_in_seconds === 'number'
    && Number.isFinite(result.resend_in_seconds)
    && result.channel === channel
    && typeof result.contact === 'string'
    && result.intent === intent
    && (result.development_code === undefined || typeof result.development_code === 'string')
}

function Icon({ name, size = 21 }: { name: string; size?: number }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true as const }
  const content: Record<string, ReactNode> = {
    home: <><path d="m3 10 9-7 9 7"/><path d="M5 9v11h14V9M9 20v-6h6v6"/></>,
    search: <><circle cx="10.8" cy="10.8" r="7.3"/><path d="m16.2 16.2 4.3 4.3"/></>,
    chat: <><path d="M20 11.5a7.7 7.7 0 0 1-8 7.5 8.8 8.8 0 0 1-3.7-.8L4 20l1.4-3.4A7.2 7.2 0 0 1 4 12c0-4.1 3.6-7.5 8-7.5s8 3.1 8 7Z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/></>,
    qr: <><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4z"/><path d="M14 14h2v2h-2zM18 14h2M18 18v2M14 18v2M20 20h-2"/></>,
    receipt: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6M9 16h3"/></>,
    user: <><circle cx="12" cy="8" r="3.5"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/></>,
    pin: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.4"/></>,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
    arrow: <><path d="M5 12h14M13 5l7 7-7 7"/></>,
    back: <><path d="m15 18-6-6 6-6"/></>,
    close: <><path d="m18 6-12 12M6 6l12 12"/></>,
    check: <><path d="m5 12 4 4L19 6"/></>,
    shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    heart: <path d="M20.8 8.8c0 5-8.8 10-8.8 10s-8.8-5-8.8-10a4.8 4.8 0 0 1 8.8-2.4 4.8 4.8 0 0 1 8.8 2.4Z"/>,
    star: <path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.2 2.1-2 2-2.2-1.2-.2.1a7.5 7.5 0 0 1-1.8.7l-.2.1-.7 2.4h-2.8l-.7-2.4-.2-.1a7.5 7.5 0 0 1-1.8-.7l-.2-.1L5.9 19l-2-2 1.2-2.1.1-.2a7.5 7.5 0 0 1-.7-1.8l-.1-.2L2 12v-2.8l2.4-.7.1-.2a7.5 7.5 0 0 1 .7-1.8l-.1-.2L3.9 4.2l2-2 2.1 1.2.2.1a7.5 7.5 0 0 1 1.8-.7l.2-.1L10.9.3h2.8l.7 2.4.2.1a7.5 7.5 0 0 1 1.8.7l.2-.1 2.1-1.2 2 2-1.2 2.1-.1.2a7.5 7.5 0 0 1 .7 1.8l.1.2 2.4.7V12l-2.4.7-.1.2a7.5 7.5 0 0 1-.7 1.8Z" transform="translate(1 1) scale(.91)"/></>,
    lock: <><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></>,
  }
  return <svg {...common}>{content[name] || content.info}</svg>
}

function Brand({ small = false }: { small?: boolean }) {
  return <div className={`brand ${small ? 'brand-small' : ''}`} aria-label="ONPay">
    <span className="brand-mark"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm1.8 17V9.4l2.6 2.6 1.7-1.7L12 4.2l-6.1 6.1 1.7 1.7 2.6-2.6V19Z"/></svg></span>
    <span className="brand-word"><b>ON</b>Pay</span>
  </div>
}

function Avatar({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' | 'lg' }) {
  return <span className={`avatar avatar-${size}`} aria-label={name}>{initials(name)}</span>
}

function Illustration() {
  return <div className="exchange-art" aria-hidden="true"><svg viewBox="0 0 400 190" role="img">
    <defs><linearGradient id="sky" x1="0" x2="1"><stop stopColor="#eef6ff"/><stop offset="1" stopColor="#f7fbff"/></linearGradient></defs>
    <rect x="4" y="8" width="392" height="174" rx="28" fill="url(#sky)"/>
    <path d="M20 130h360v43H20z" fill="#d9e8ff"/><path d="M33 74h74v58H33z" fill="#d2e2f6"/><path d="M43 87h17v17H43zm34 0h17v17H77zm-34 29h17v16H43zm34 0h17v16H77z" fill="#fff"/>
    <path d="M296 64h74v69h-74z" fill="#e6effb"/><path d="M306 78h17v17h-17zm34 0h17v17h-17zm-34 29h17v17h-17zm34 0h17v17h-17z" fill="#fff"/>
    <circle cx="76" cy="117" r="18" fill="#92c77e"/><path d="M76 132v31m-17-12h34m-28-8-11 16m34-16 11 16" stroke="#6b9f62" strokeWidth="6" strokeLinecap="round"/>
    <circle cx="344" cy="119" r="18" fill="#92c77e"/><path d="M344 134v29m-17-11h34m-28-8-10 15m33-15 10 15" stroke="#6b9f62" strokeWidth="6" strokeLinecap="round"/>
    <circle cx="158" cy="72" r="21" fill="#e7aa83"/><path d="M136 70c2-23 42-28 45 1-9-6-20-8-30-5-5 2-10 4-15 4Z" fill="#26344c"/>
    <path d="M128 102c9-14 50-14 60 0l9 47h-77z" fill="#1661e8"/><path d="M132 110 114 137m47-25 22 23" stroke="#e7aa83" strokeWidth="10" strokeLinecap="round"/>
    <circle cx="243" cy="73" r="21" fill="#b97856"/><path d="M222 71c1-21 39-30 44-1-11-7-25-6-44 1Z" fill="#192337"/>
    <path d="M210 103c10-15 52-15 63 0l7 46h-76z" fill="#1b9d63"/><path d="m217 110-17 25m47-24-27 17" stroke="#b97856" strokeWidth="10" strokeLinecap="round"/>
    <path d="M185 125h31" stroke="#253650" strokeWidth="5" strokeLinecap="round"/><rect x="185" y="112" width="31" height="23" rx="4" fill="#fff" stroke="#d6e2f2"/><path d="M193 119h15m-15 5h11" stroke="#0759ed" strokeWidth="2" strokeLinecap="round"/>
    <circle cx="200" cy="35" r="14" fill="#fff"/><path d="M200 42V28m-5 5 5-5 5 5" stroke="#0759ed" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg></div>
}

function Welcome({ onStart, onLogin }: { onStart: () => void; onLogin: () => void }) {
  return <main className="auth-shell welcome-shell">
    <div className="auth-brand"><Brand/><p>Cash When You Need It.<br/><strong>Digital When You Have It.</strong></p><span className="student-badge"><span>✦</span> Built for Students</span></div>
    <Illustration/>
    <div className="welcome-points"><span><b className="point-icon blue">◎</b><strong>Nearby students</strong></span><span><b className="point-icon green">✓</b><strong>Safer meetups</strong></span><span><b className="point-icon violet">↗</b><strong>Simple process</strong></span></div>
    <div className="auth-actions"><button className="button button-primary button-wide" onClick={onStart}>Get started <Icon name="arrow"/></button><p>Already have an account? <button className="link-button" onClick={onLogin}>Log in</button></p></div>
    <p className="fine-print">ONPay coordinates exchanges. Payments happen in your UPI app.</p>
  </main>
}

function AuthForm({ intent, onOtp, onChangeIntent, busy, setError }: { intent: 'signup' | 'login'; onOtp: (challenge: OtpRequestResult) => void; onChangeIntent: (intent: 'signup' | 'login') => void; busy: boolean; setError: (message: string) => void }) {
  const [channel, setChannel] = useState<OtpChannel>('mobile')
  const [name, setName] = useState('')
  const [contact, setContact] = useState('')
  const [college, setCollege] = useState('')
  const [agreed, setAgreed] = useState(true)
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError('')
    if (intent === 'signup' && !agreed) { setError('Please agree to the Terms and Privacy Policy to continue.'); return }
    setSending(true)
    try {
      const result = await api<unknown>('/api/auth/otp/request', json({ channel, contact, intent, ...(intent === 'signup' ? { full_name: name, college } : {}) }))
      if (!isAcceptedOtpRequest(result, channel, intent)) throw new Error('The server did not confirm the verification request. Please try again later.')
      setSent(true); onOtp({ ...result, channel, contact: contact.trim(), intent, full_name: name, college })
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not send a verification code.') } finally { setSending(false) }
  }
  return <main className="auth-shell form-shell">
    <div className="auth-topline"><button className="icon-button" onClick={() => onChangeIntent('login')} aria-label="Back"><Icon name="back"/></button><button className="link-button" onClick={() => onChangeIntent(intent === 'signup' ? 'login' : 'signup')}>{intent === 'signup' ? 'Log in' : 'Sign up'}</button></div>
    <div className="auth-brand compact"><Brand/><span className="student-badge"><span>✦</span> Built for Students</span></div>
    <section className="auth-card">
      <h1>{intent === 'signup' ? 'Create your account' : 'Welcome back'}</h1>
      <p className="muted">{intent === 'signup' ? 'Join ONPay and exchange cash easily.' : 'Log in securely with a one-time code.'}</p>
      <div className="segmented auth-tabs" role="tablist" aria-label="Verification method">
        <button type="button" className={channel === 'mobile' ? 'selected' : ''} onClick={() => setChannel('mobile')}><Icon name="user" size={18}/> Mobile</button>
        <button type="button" className={channel === 'email' ? 'selected' : ''} onClick={() => setChannel('email')}><Icon name="info" size={18}/> Email</button>
      </div>
      <form onSubmit={submit} className="stack-form">
        {intent === 'signup' && <label>Full name<input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder="Enter your full name" autoComplete="name"/></label>}
        <label>{channel === 'mobile' ? 'Mobile number' : 'Email address'}
          <input required type={channel === 'mobile' ? 'tel' : 'email'} value={contact} onChange={(e) => setContact(e.target.value)} placeholder={channel === 'mobile' ? '+91 98765 43210' : 'you@example.com'} autoComplete={channel === 'mobile' ? 'tel' : 'email'}/>
        </label>
        {intent === 'signup' && <label>College <span className="optional">(optional)</span><input maxLength={140} value={college} onChange={(e) => setCollege(e.target.value)} placeholder="Enter your college or university"/></label>}
        {intent === 'signup' && <label className="check-row"><input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)}/><span>I agree to ONPay’s <button type="button" className="inline-link" onClick={() => setError('Terms and Privacy Policy: ONPay uses your verified contact for account access and stores the campus or meeting label you choose.')}>Terms</button> and <button type="button" className="inline-link" onClick={() => setError('Privacy: when you allow location, ONPay sends coordinates to its API for nearby matching and reverse geocoding. New listings store only a rounded approximate point; exact coordinates are never returned to other students.')}>Privacy Policy</button>.</span></label>}
        <button className="button button-primary button-wide" disabled={busy || sending}>{busy || sending ? 'Sending code…' : sent ? 'Send a new code' : 'Send OTP'} <Icon name="arrow"/></button>
      </form>
      <div className="safe-note"><Icon name="lock" size={16}/> Your one-time code stays private. Never share your UPI PIN.</div>
    </section>
    <Illustration/>
    <p className="auth-switch">{intent === 'signup' ? 'Already have an account?' : 'New to ONPay?'} <button className="link-button" onClick={() => onChangeIntent(intent === 'signup' ? 'login' : 'signup')}>{intent === 'signup' ? 'Log in' : 'Create account'}</button></p>
  </main>
}

function VerifyScreen({ challenge, onBack, onSuccess, onChallenge, setError }: { challenge: any; onBack: () => void; onSuccess: () => Promise<void>; onChallenge: (challenge: any) => void; setError: (message: string) => void }) {
  const [code, setCode] = useState(challenge?.development_code || '')
  const [busy, setBusy] = useState(false)
  const [resending, setResending] = useState(false)
  const [resendIn, setResendIn] = useState(challenge?.resend_in_seconds || 0)
  useEffect(() => {
    setResendIn(challenge?.resend_in_seconds || 0)
    const timer = window.setInterval(() => setResendIn((seconds: number) => Math.max(0, seconds - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [challenge?.challenge_id, challenge?.resend_in_seconds])
  const verify = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setBusy(true)
    try { await api('/api/auth/otp/verify', json({ challenge_id: challenge.challenge_id, code })); await onSuccess() }
    catch (error) { setError(error instanceof Error ? error.message : 'Could not verify that code.') } finally { setBusy(false) }
  }
  const resend = async () => {
    if (resendIn > 0 || resending) return
    setError(''); setResending(true)
    try {
      const next = await api<unknown>('/api/auth/otp/request', json({ channel: challenge.channel, contact: challenge.contact, intent: challenge.intent, full_name: challenge.full_name, college: challenge.college }))
      if (!isAcceptedOtpRequest(next, challenge.channel, challenge.intent)) throw new Error('The server did not confirm the new verification request. Please try again later.')
      const updated = { ...next, channel: challenge.channel, contact: challenge.contact, intent: challenge.intent, full_name: challenge.full_name, college: challenge.college }
      onChallenge(updated); setCode(updated.development_code || '')
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not send a new code.') } finally { setResending(false) }
  }
  const contactLabel = challenge?.contact || 'your contact'
  return <main className="auth-shell verify-shell">
    <button className="icon-button back-abs" onClick={onBack} aria-label="Back"><Icon name="back"/></button>
    <div className="verify-icon"><Icon name="lock" size={25}/></div><Brand small/>
    <h1>Verify your contact</h1><p className="muted">If this contact can continue, a 6-digit code was sent to<br/><strong>{contactLabel}</strong></p>
    {challenge?.development_code && <div className="dev-code"><span>Local development code</span><b>{challenge.development_code}</b></div>}
    <form onSubmit={verify} className="stack-form otp-form"><label>Verification code<input inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="[0-9]{6}" required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="••••••"/></label><button className="button button-primary button-wide" disabled={busy}>{busy ? 'Verifying…' : 'Verify and continue'} <Icon name="arrow"/></button></form>
    <p className="muted small-centered">The code expires in 5 minutes.</p><button type="button" className="link-button resend-code" onClick={resend} disabled={resending || resendIn > 0}>{resending ? 'Sending a new code…' : resendIn > 0 ? `Resend available in ${resendIn}s` : 'Resend code'}</button>
  </main>
}

function Notice({ message, onClose }: { message: string; onClose: () => void }) {
  if (!message) return null
  return <div className="notice" role="status"><Icon name="info" size={18}/><span>{message}</span><button className="icon-button" onClick={onClose} aria-label="Dismiss"><Icon name="close" size={17}/></button></div>
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [screen, setScreen] = useState<Screen>('welcome')
  const [authIntent, setAuthIntent] = useState<'signup' | 'login'>('signup')
  const [challenge, setChallenge] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [locationLabel, setLocationLabel] = useState(localStorage.getItem('onpay-location') || '')
  const [geoCoordinates, setGeoCoordinates] = useState<Coordinates | null>(null)
  const [geoDetails, setGeoDetails] = useState<ResolvedLocation | null>(null)
  const [geoLabel, setGeoLabel] = useState('')
  const [geoStatus, setGeoStatus] = useState<GeoStatus>('checking')
  const [geoMessage, setGeoMessage] = useState('')
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null)
  const [selectedExchange, setSelectedExchange] = useState<Exchange | null>(null)
  const [chatTarget, setChatTarget] = useState<string | null>(null)
  const [payment, setPayment] = useState<Payment | null>(null)
  const [unreadCount, setUnreadCount] = useState(0)

  useEffect(() => {
    let active = true
    const restore = async () => {
      const session = await restoreAuthSession<User>((path) => api(path))
      if (!active) return
      if (session.status === 'authenticated') {
        const restoredUser = session.user
        setUser(restoredUser)
        const savedLocation = restoredUser.location_label || ''
        setLocationLabel(savedLocation)
        if (savedLocation) localStorage.setItem('onpay-location', savedLocation)
        else localStorage.removeItem('onpay-location')
        const allowed: Screen[] = ['home', 'matches', 'chats', 'scan', 'transactions', 'profile', 'need', 'have', 'meetup', 'notifications', 'subscriptions', 'points', 'location', 'help']
        const destination = window.location.hash.slice(1) as Screen
        setScreen(allowed.includes(destination) ? destination : 'home')
        api('/api/notifications').then((notifications) => setUnreadCount(notifications.unread_count)).catch(() => setUnreadCount(0))
      } else if (session.status === 'error') {
        setError('The ONPay service is unavailable. Start the API and try again.')
      }
      setReady(true)
    }
    void restore()
    return () => { active = false }
  }, [])

  const refreshLocation = useCallback(() => {
    setGeoStatus('loading'); setGeoMessage(''); setGeoDetails(null); setGeoCoordinates(null); setGeoLabel('')
    detectCurrentLocation({
      geolocation: navigator.geolocation,
      isSecureContext: window.isSecureContext,
      hostname: window.location.hostname,
      reverseGeocode: async (position) => {
        const query = new URLSearchParams({
          latitude: String(position.latitude),
          longitude: String(position.longitude),
        })
        return api(`/api/location/reverse?${query.toString()}`)
      },
    }).then((position) => {
      setGeoCoordinates({ latitude: position.latitude, longitude: position.longitude })
      setGeoDetails(position)
      setGeoLabel(position.placeName)
      setGeoMessage(position.message)
      setGeoStatus('ready')
    }).catch((failure: Error & { code?: string }) => {
      setGeoCoordinates(null)
      setGeoDetails(null)
      setGeoLabel('')
      setGeoStatus(failure.code === 'permission_denied' ? 'denied' : failure.code === 'timeout' ? 'error' : failure.code === 'insecure_origin' ? 'insecure' : 'unavailable')
      setGeoMessage(failure.message)
    })
  }, [])

  useEffect(() => {
    if (!user || screen !== 'home') return
    if (!navigator.geolocation) { setGeoStatus('unavailable'); setGeoMessage('This browser does not support location. Choose your campus manually.'); return }
    if (!navigator.permissions?.query) { setGeoStatus('prompt'); setGeoMessage('Location is optional. Select Use current location to grant permission, or enter a campus manually.'); return }
    let active = true
    const update = (state: PermissionState) => {
      if (!active) return
      if (state === 'granted') refreshLocation()
      else if (state === 'denied') { setGeoCoordinates(null); setGeoDetails(null); setGeoLabel(''); setGeoStatus('denied'); setGeoMessage('Location access was denied. Allow location in this site’s browser settings, or choose a campus manually.') }
      else { setGeoCoordinates(null); setGeoDetails(null); setGeoLabel(''); setGeoStatus('prompt'); setGeoMessage('Location is optional. Select Use current location to grant permission, or enter a campus manually.') }
    }
    let permissionStatus: PermissionStatus | null = null
    navigator.permissions.query({ name: 'geolocation' }).then((result) => {
      permissionStatus = result; update(result.state)
      result.onchange = () => update(result.state)
    }).catch(() => { setGeoCoordinates(null); setGeoDetails(null); setGeoLabel(''); setGeoStatus('prompt') })
    return () => { active = false; if (permissionStatus) permissionStatus.onchange = null }
  }, [user?.id, screen, refreshLocation])

  const navigate = useCallback((next: Screen) => { setScreen(next); setError(''); window.location.hash = next }, [])
  const signIn = async () => {
    const session = await restoreAuthSession<User>((path) => api(path))
    if (session.status !== 'authenticated') {
      if (session.status === 'error' && session.error instanceof Error) throw session.error
      throw new ApiError('ONPay could not confirm your sign-in session. Please try again.', 401)
    }
    const nextUser = session.user
    setUser(nextUser); setLocationLabel(nextUser.location_label || ''); setGeoCoordinates(null); setGeoDetails(null); setGeoLabel(''); setGeoStatus('checking'); setScreen('home'); setChallenge(null); setError(''); window.location.hash = 'home'
  }
  const signOut = async () => { try { await api('/api/auth/logout', { method: 'POST' }) } catch {} setUser(null); setGeoCoordinates(null); setGeoDetails(null); setGeoLabel(''); setScreen('welcome'); setPayment(null); window.location.hash = '' }
  const saveLocation = async (label: string) => {
    try { await api('/api/location/settings', patch({ label })); setLocationLabel(label); if (label) localStorage.setItem('onpay-location', label); else localStorage.removeItem('onpay-location'); setError('') }
    catch (failure) { const message = failure instanceof Error ? failure.message : 'Could not save location'; setError(message); throw failure }
  }

  const authState = getAuthState(ready, user)
  if (authState === 'loading') return <div className="loading-screen"><Brand/><span className="spinner"/></div>
  if (authState === 'unauthenticated') return <div className="app-outer"><Notice message={error} onClose={() => setError('')}/>{screen === 'verify' && challenge ? <VerifyScreen challenge={challenge} setError={setError} onChallenge={setChallenge} onBack={() => navigate(authIntent)} onSuccess={signIn}/> : screen === 'signup' || screen === 'login' ? <AuthForm intent={screen} busy={busy} setError={setError} onChangeIntent={(intent) => { setAuthIntent(intent); navigate(intent) }} onOtp={(nextChallenge) => { setChallenge(nextChallenge); setAuthIntent(nextChallenge.intent); navigate('verify') }}/> : <Welcome onStart={() => { setAuthIntent('signup'); navigate('signup') }} onLogin={() => { setAuthIntent('login'); navigate('login') }}/>}</div>
  if (!user) return <div className="loading-screen"><Brand/><span className="spinner"/></div>

  const activeNav: Screen = screen === 'need' || screen === 'have' || screen === 'matches' || screen === 'student' ? 'home' : screen === 'meetup' || screen === 'payment' ? 'transactions' : screen
  return <div className="app-outer">
    <div className="app-frame">
      <header className="topbar">
        <button className="top-location" onClick={() => navigate('location')}><span className="location-pin"><Icon name="pin" size={16}/></span><span><strong>{geoLabel || locationLabel || (geoStatus === 'loading' || geoStatus === 'checking' ? 'Finding your location…' : 'Choose your campus')}</strong><small>{geoLabel ? 'Approximate current area' : locationLabel ? 'Selected area' : 'Set a location for nearby matches'}</small></span><span className="chevron">⌄</span></button>
        <button className="icon-button notification-trigger" onClick={() => navigate('notifications')} aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}><Icon name="bell"/>{unreadCount > 0 && <span className="unread-dot"/>}</button>
        <button className="avatar-button" onClick={() => navigate('profile')} aria-label="Profile"><Avatar name={user.full_name} size="sm"/></button>
      </header>

      <main className="content-area">
        <Notice message={error} onClose={() => setError('')}/>
        {screen === 'home' && <HomePage user={user} locationLabel={locationLabel} geoLabel={geoLabel} geoStatus={geoStatus} geoMessage={geoMessage} coordinates={geoCoordinates} refreshLocation={refreshLocation} navigate={navigate} setLocation={saveLocation} setSelectedListing={setSelectedListing} setSelectedExchange={setSelectedExchange}/>}
        {screen === 'need' && <ListingForm kind="need" locationLabel={geoLabel || locationLabel} coordinates={geoCoordinates} navigate={navigate} setError={setError}/>}
        {screen === 'have' && <ListingForm kind="have" locationLabel={geoLabel || locationLabel} coordinates={geoCoordinates} navigate={navigate} setError={setError}/>}
        {screen === 'matches' && <MatchesPage coordinates={geoCoordinates} geoStatus={geoStatus} navigate={navigate} setSelectedListing={setSelectedListing} setSelectedExchange={setSelectedExchange} setError={setError}/>}
        {screen === 'student' && selectedListing && <StudentPage listing={selectedListing} navigate={navigate} setChatTarget={setChatTarget} setError={setError}/>}
        {screen === 'chats' && <ChatsPage targetUserId={chatTarget} user={user} setChatTarget={setChatTarget} setError={setError}/>}
        {screen === 'scan' && <ScannerPage user={user} exchangesAction={setSelectedExchange} navigate={navigate} payment={payment} setPayment={setPayment} setError={setError}/>}
        {screen === 'transactions' && <TransactionsPage navigate={navigate} setSelectedExchange={setSelectedExchange}/>}
        {screen === 'meetup' && <MeetupPage user={user} selected={selectedExchange} setSelected={setSelectedExchange} navigate={navigate} setError={setError}/>}
        {screen === 'payment' && payment && <PaymentPage payment={payment} setPayment={setPayment} navigate={navigate}/>}
        {screen === 'notifications' && <NotificationsPage onRead={() => setUnreadCount((count) => Math.max(0, count - 1))}/>}
        {screen === 'profile' && <ProfilePage user={user} setUser={setUser} navigate={navigate} signOut={signOut} setError={setError}/>}
        {screen === 'subscriptions' && <SubscriptionsPage/>}
        {screen === 'points' && <PointsPage/>}
        {screen === 'location' && <LocationPage current={locationLabel} geoLabel={geoLabel} geoDetails={geoDetails} geoStatus={geoStatus} geoMessage={geoMessage} refreshLocation={refreshLocation} save={saveLocation}/>}
        {screen === 'help' && <HelpPage/>}
      </main>

      <nav className="bottom-nav" aria-label="Main navigation">
        <NavItem active={activeNav === 'home'} icon="home" label="Home" onClick={() => navigate('home')}/>
        <NavItem active={activeNav === 'chats'} icon="chat" label="Chats" onClick={() => { setChatTarget(null); navigate('chats') }}/>
        <button className="nav-scan" onClick={() => { setPayment(null); navigate('scan') }} aria-label="Open QR scanner"><span><Icon name="qr" size={24}/></span><small>Scan</small></button>
        <NavItem active={activeNav === 'transactions'} icon="receipt" label="Activity" onClick={() => navigate('transactions')}/>
        <NavItem active={activeNav === 'profile'} icon="user" label="Profile" onClick={() => navigate('profile')}/>
      </nav>
    </div>
  </div>
}

function NavItem({ active, icon, label, onClick }: { active: boolean; icon: string; label: string; onClick: () => void }) {
  return <button className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}><Icon name={icon} size={20}/><span>{label}</span></button>
}

function PageTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="page-heading"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{action}</div>
}

function EmptyState({ icon = 'search', title, body, action }: { icon?: string; title: string; body: string; action?: React.ReactNode }) {
  return <div className="empty-state"><span className="empty-icon"><Icon name={icon} size={27}/></span><h3>{title}</h3><p>{body}</p>{action}</div>
}

function HomePage({ user, locationLabel, geoLabel, geoStatus, geoMessage, coordinates, refreshLocation, navigate, setLocation, setSelectedListing, setSelectedExchange }: { user: User; locationLabel: string; geoLabel: string; geoStatus: GeoStatus; geoMessage: string; coordinates: Coordinates | null; refreshLocation: () => void; navigate: (screen: Screen) => void; setLocation: (label: string) => void; setSelectedListing: (listing: Listing) => void; setSelectedExchange: (exchange: Exchange) => void }) {
  const [listings, setListings] = useState<Listing[]>([])
  const [mine, setMine] = useState<any[]>([])
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => {
    try {
      const query = new URLSearchParams()
      if (coordinates) { query.set('latitude', String(coordinates.latitude)); query.set('longitude', String(coordinates.longitude)); query.set('radius_km', '25') }
      const [nearby, own, activity] = await Promise.all([api(`/api/listings${query.size ? `?${query}` : ''}`), api('/api/my-listings'), api('/api/exchanges')])
      setListings(nearby.listings.slice(0, 3)); setMine(own.listings.filter((item: any) => item.status !== 'cancelled')); setExchanges(activity.exchanges.slice(0, 2))
    } catch { setListings([]) } finally { setLoading(false) }
  }, [coordinates])
  useEffect(() => { load() }, [load])
  const useLocation = () => { if (geoStatus === 'loading' || geoStatus === 'checking') return; if (geoStatus === 'denied' || geoStatus === 'unavailable') navigate('location'); else refreshLocation() }
  const displayedArea = geoLabel || locationLabel
  return <div className="page-stack">
    <section className="home-greeting"><div><span className="eyebrow">WELCOME BACK</span><h1>Hi, {user.full_name.split(' ')[0]} <span>👋</span></h1><p>What do you need today?</p></div><div className="home-points"><b>{user.points}</b><small>points</small></div></section>
    <button className={`campus-banner ${displayedArea ? 'has-location' : ''}`} onClick={useLocation}><span className="campus-icon">{geoStatus === 'loading' || geoStatus === 'checking' ? <span className="spinner small-spinner"/> : <Icon name="pin"/>}</span><span><strong>{displayedArea || (geoStatus === 'loading' || geoStatus === 'checking' ? 'Finding your current area…' : geoStatus === 'denied' ? 'Location access is blocked' : 'Enable location for nearby matches')}</strong><small>{geoMessage || (coordinates ? 'Listings are filtered using your approximate current area.' : 'Location is optional; you can choose a campus manually.')}</small></span><span className="banner-action">{geoStatus === 'denied' || geoStatus === 'unavailable' ? 'Settings' : coordinates ? 'Refresh' : 'Enable'} <Icon name="arrow" size={16}/></span></button>
    <section className="action-grid">
      <button className="action-card need-card" onClick={() => navigate('need')}><span className="action-icon"><Icon name="arrow"/></span><strong>I need cash</strong><small>Pay digitally and receive cash</small><b className="card-link">Find a match <Icon name="arrow" size={16}/></b></button>
      <button className="action-card have-card" onClick={() => navigate('have')}><span className="action-icon"><Icon name="check"/></span><strong>I have cash</strong><small>Give cash and receive UPI</small><b className="card-link">Publish an offer <Icon name="arrow" size={16}/></b></button>
    </section>
    <section className="section-block">
      <div className="section-title"><div><h2>Nearby activity</h2><p>Students who have chosen to share a listing</p></div><button className="text-action" onClick={() => navigate('matches')}>View all <Icon name="arrow" size={15}/></button></div>
      {loading ? <div className="loading-inline"><span className="spinner"/>Loading listings…</div> : listings.length ? <div className="listing-stack">{listings.map((listing) => <ListingCard key={listing.id} listing={listing} onClick={() => { setSelectedListing(listing); navigate('student') }}/>)}</div> : <EmptyState title="No nearby listings yet" body="When students post a cash request or offer, it will show here. Your home feed does not use sample profiles." action={<button className="button button-soft" onClick={() => navigate('matches')}>Explore listings</button>}/>}</section>
    <section className="section-block recent-block"><div className="section-title"><div><h2>Your exchanges</h2><p>Meetups and payment status, together</p></div><button className="text-action" onClick={() => navigate('transactions')}>See all <Icon name="arrow" size={15}/></button></div>
      {exchanges.length ? <div className="exchange-mini-list">{exchanges.map((exchange) => <button key={exchange.id} className="exchange-mini" onClick={() => { setSelectedExchange(exchange); navigate('meetup') }}><Avatar name={exchange.other_user?.full_name || 'Student'} size="sm"/><span><strong>{exchange.other_user?.full_name}</strong><small>{exchange.status.replaceAll('_', ' ')}</small></span><b>{money(exchange.amount)}</b></button>)}</div> : <p className="quiet-empty">No exchanges started yet. Your matches will appear here.</p>}
    </section>
    {mine.length > 0 && <section className="own-listings"><div className="section-title"><div><h2>Your listings</h2><p>You can pause or cancel an active listing.</p></div></div>{mine.slice(0, 2).map((listing) => <div className="own-listing" key={listing.id}><span className={`listing-kind ${listing.kind}`}>{listing.kind === 'need' ? 'Need cash' : 'Have cash'}</span><strong>{money(listing.amount_min)}{listing.amount_max !== listing.amount_min ? `–${money(listing.amount_max)}` : ''}</strong><span className="status-pill neutral">{listing.status}</span></div>)}</section>}
    <section className="safety-tip"><span><Icon name="shield"/></span><div><strong>Keep exchanges safe</strong><p>Meet in a public campus spot. ONPay never asks for your UPI PIN.</p></div><button onClick={() => navigate('help')} aria-label="Safety tips"><Icon name="arrow" size={16}/></button></section>
  </div>
}

function ListingCard({ listing, onClick }: { listing: Listing; onClick: () => void }) {
  return <button className="listing-card" onClick={onClick}>
    <Avatar name={listing.owner.full_name} size="md"/>
    <span className="listing-info"><span className="listing-name">{listing.owner.full_name} {listing.owner.verified && <span className="verified-dot" title="Contact verified"><Icon name="check" size={11}/></span>}</span><small>{listing.owner.college || 'Student'} · {listing.location}{listing.distance_km != null ? ` · ${listing.distance_km} km away` : ''}</small><span className={`listing-kind ${listing.kind}`}>{listing.kind === 'need' ? 'Needs cash' : 'Has cash'}</span></span>
    <span className="listing-amount"><strong>{money(listing.amount_min)}{listing.amount_max !== listing.amount_min ? `–${money(listing.amount_max)}` : ''}</strong><small>{listing.availability}</small></span>
  </button>
}

function ListingForm({ kind, locationLabel, coordinates, navigate, setError }: { kind: 'need' | 'have'; locationLabel: string; coordinates: Coordinates | null; navigate: (screen: Screen) => void; setError: (message: string) => void }) {
  const [minimum, setMinimum] = useState('')
  const [maximum, setMaximum] = useState('')
  const [location, setLocation] = useState(locationLabel)
  const [availability, setAvailability] = useState('Today, 2:00 PM – 4:00 PM')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const isNeed = kind === 'need'
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setError('')
    try {
      const min = Math.round(Number(minimum) * 100); const max = isNeed ? min : Math.round(Number(maximum || minimum) * 100)
      await api('/api/listings', json({ kind, amount_min: min, amount_max: max, location, availability, note, ...(coordinates || {}) }))
      navigate('home')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not publish this listing') } finally { setSaving(false) }
  }
  return <div className="page-stack form-page"><PageTitle title={isNeed ? 'Request cash' : 'Offer cash'} subtitle={isNeed ? 'Find a student who can exchange cash for your UPI payment.' : 'Share how much cash you can exchange for a UPI payment.'} action={<button className="icon-button" onClick={() => navigate('home')} aria-label="Close"><Icon name="close"/></button>}/>
    <div className={`form-hero ${isNeed ? 'blue-hero' : 'green-hero'}`}><span className="form-hero-icon"><Icon name={isNeed ? 'arrow' : 'check'} size={24}/></span><div><b>{isNeed ? 'I Need Cash' : 'I Have Cash'}</b><small>{isNeed ? 'You pay in your UPI app after meeting.' : 'You receive the UPI payment after handing over cash.'}</small></div></div>
    <form className="panel stack-form" onSubmit={submit}>
      <label>{isNeed ? 'Cash amount' : 'Available cash'}<div className="money-input"><span>₹</span><input type="number" required min="1" max="2500" step="1" value={minimum} onChange={(e) => setMinimum(e.target.value)} placeholder="500"/></div><small className="field-hint">Choose an amount from ₹1 to ₹2,500 for this exchange.</small></label>
      {!isNeed && <label>Minimum amount for partial exchanges <span className="optional">(optional)</span><div className="money-input"><span>₹</span><input type="number" min="1" max="2500" step="1" value={maximum} onChange={(e) => setMaximum(e.target.value)} placeholder="Same as available cash"/></div></label>}
      <label>Meeting location<input required minLength={2} maxLength={180} value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Library entrance, Aditya University"/><small className="field-hint">Use a public place. If location is enabled, ONPay uses a rounded approximate position for nearby matching; exact coordinates are never shown.</small></label>
      <label>Preferred time<input required maxLength={120} value={availability} onChange={(e) => setAvailability(e.target.value)} placeholder="Today after 3 PM"/></label>
      <label>Note <span className="optional">(optional)</span><textarea maxLength={500} rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder={isNeed ? 'e.g. Need cash for lunch' : 'e.g. Can meet near the main gate'}/></label>
      <button className={`button button-primary button-wide ${isNeed ? '' : 'button-green'}`} disabled={saving}>{saving ? 'Publishing…' : isNeed ? 'Find a match' : 'Publish offer'} <Icon name="arrow"/></button>
    </form>
    <div className="safe-note"><Icon name="info" size={17}/> Creating a listing does not initiate a payment or confirm an exchange.</div>
  </div>
}

function MatchesPage({ coordinates, geoStatus, navigate, setSelectedListing, setSelectedExchange, setError }: { coordinates: Coordinates | null; geoStatus: GeoStatus; navigate: (screen: Screen) => void; setSelectedListing: (listing: Listing) => void; setSelectedExchange: (exchange: Exchange) => void; setError: (message: string) => void }) {
  const [filter, setFilter] = useState('all')
  const [draft, setDraft] = useState({ minimum: '', maximum: '', location: '', availability: '' })
  const [filters, setFilters] = useState(draft)
  const [listings, setListings] = useState<Listing[]>([])
  const [mine, setMine] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState('')
  const [sort, setSort] = useState('recent')
  const load = useCallback(async () => {
    setLoading(true)
    const query = new URLSearchParams({ kind: filter })
    if (coordinates) { query.set('latitude', String(coordinates.latitude)); query.set('longitude', String(coordinates.longitude)); query.set('radius_km', '25') }
    if (filters.minimum) query.set('min_amount', String(Math.round(Number(filters.minimum) * 100)))
    if (filters.maximum) query.set('max_amount', String(Math.round(Number(filters.maximum) * 100)))
    if (filters.location.trim()) query.set('location', filters.location.trim())
    if (filters.availability.trim()) query.set('availability', filters.availability.trim())
    try { const [data, own] = await Promise.all([api(`/api/listings?${query.toString()}`), api('/api/my-listings')]); setListings(data.listings); setMine(own.listings.filter((item: any) => item.status === 'active')) }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not load matches') }
    finally { setLoading(false) }
  }, [filter, filters, coordinates, setError])
  useEffect(() => { load() }, [load])
  const ordered = useMemo(() => [...listings].sort((a, b) => sort === 'amount' ? a.amount_min - b.amount_min : 0), [listings, sort])
  const match = async (listing: Listing) => {
    const expectedKind = listing.kind === 'need' ? 'have' : 'need'
    const ownListing = mine.find((item) => item.kind === expectedKind && Math.max(item.amount_min, listing.amount_min) <= Math.min(item.amount_max, listing.amount_max))
    if (!ownListing) { setError(`Create an active ${expectedKind === 'have' ? 'cash offer' : 'cash request'} with a compatible amount first.`); navigate(expectedKind); return }
    const amount = Math.max(ownListing.amount_min, listing.amount_min)
    setBusyId(listing.id); setError('')
    try { const data = await api(`/api/listings/${listing.id}/accept`, json({ amount })); setSelectedExchange(data.exchange); navigate('meetup') }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'This match is no longer available') }
    finally { setBusyId('') }
  }
  return <div className="page-stack"><PageTitle title="Nearby matches" subtitle={coordinates ? 'Active listings within 25 km of your approximate current area.' : geoStatus === 'denied' ? 'Location is blocked; browse all listings or choose a campus area.' : 'Enable location to filter by distance, or browse all active listings.'}/>
    <div className="filter-row">{[['all', 'All'], ['need', 'Need cash'], ['have', 'Have cash']].map(([value, label]) => <button key={value} className={`filter-chip ${filter === value ? 'selected' : ''}`} onClick={() => setFilter(value)}>{label}</button>)}</div>
    <form className="match-filter-panel" onSubmit={(event) => { event.preventDefault(); setFilters({ ...draft }) }}><label>Minimum ₹<input type="number" min="1" step="1" value={draft.minimum} onChange={(event) => setDraft({ ...draft, minimum: event.target.value })} placeholder="Any"/></label><label>Maximum ₹<input type="number" min="1" step="1" value={draft.maximum} onChange={(event) => setDraft({ ...draft, maximum: event.target.value })} placeholder="Any"/></label><label>Campus or area<input maxLength={120} value={draft.location} onChange={(event) => setDraft({ ...draft, location: event.target.value })} placeholder="Any meeting area"/></label><label>Preferred time<input maxLength={80} value={draft.availability} onChange={(event) => setDraft({ ...draft, availability: event.target.value })} placeholder="Any time"/></label><button className="button button-soft">Apply filters</button><button type="button" className="text-action" onClick={() => { const clear = { minimum: '', maximum: '', location: '', availability: '' }; setDraft(clear); setFilters(clear) }}>Clear</button></form>
    <div className="sort-row"><span>{listings.length} {listings.length === 1 ? 'listing' : 'listings'}</span><label>Sort <select value={sort} onChange={(e) => setSort(e.target.value)}><option value="recent">Recently posted</option><option value="amount">Amount</option></select></label></div>
    {loading ? <div className="loading-inline"><span className="spinner"/>Finding matches…</div> : ordered.length ? <div className="match-list">{ordered.map((listing) => <article key={listing.id} className="match-card"><ListingCard listing={listing} onClick={() => { setSelectedListing(listing); navigate('student') }}/><div className="match-detail"><span><Icon name="clock" size={15}/> {listing.availability}</span><span><Icon name="pin" size={15}/> {listing.location}</span></div><div className="match-buttons"><button className="button button-soft" onClick={() => { setSelectedListing(listing); navigate('student') }}>View details</button><button className="button button-primary" disabled={busyId === listing.id} onClick={() => match(listing)}>{busyId === listing.id ? 'Matching…' : 'Match'}</button></div></article>)}</div> : <EmptyState title="No matching listings" body="Try another filter or publish a request or offer so students can find you." action={<div className="empty-actions"><button className="button button-primary" onClick={() => navigate('need')}>I need cash</button><button className="button button-soft" onClick={() => navigate('have')}>I have cash</button></div>}/>} 
  </div>
}

function StudentPage({ listing, navigate, setChatTarget, setError }: { listing: Listing; navigate: (screen: Screen) => void; setChatTarget: (id: string | null) => void; setError: (message: string) => void }) {
  const reportOrBlock = async (action: 'report' | 'block') => {
    try {
      if (action === 'block') { await api('/api/blocks', json({ user_id: listing.owner.id })); setError('Student blocked. Their listings and messages are hidden from you.') }
      else { await api('/api/reports', json({ user_id: listing.owner.id, category: 'profile_report', details: '' })); setError('Thanks. Your report has been sent for review.') }
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not submit this request') }
  }
  return <div className="page-stack"><button className="back-link" onClick={() => navigate('matches')}><Icon name="back" size={17}/> Back to matches</button><section className="student-profile panel"><Avatar name={listing.owner.full_name} size="lg"/><h1>{listing.owner.full_name}</h1><p>{listing.owner.college || 'Student'}</p>{listing.owner.verified && <span className="verified-label"><Icon name="shield" size={15}/> Contact verified</span>}<div className={`student-offer ${listing.kind}`}><span>{listing.kind === 'need' ? 'Needs cash' : 'Has cash'}</span><strong>{money(listing.amount_min)}{listing.amount_max !== listing.amount_min ? ` – ${money(listing.amount_max)}` : ''}</strong></div><div className="detail-row"><span>Meeting area</span><strong>{listing.location}</strong></div><div className="detail-row"><span>Availability</span><strong>{listing.availability}</strong></div>{listing.note && <div className="note-card">“{listing.note}”</div>}<p className="privacy-note"><Icon name="info" size={15}/> Ratings and exchange counts will appear only after real, verified exchanges.</p><button className="button button-primary button-wide" onClick={() => { setChatTarget(listing.owner.id); navigate('chats') }}>Message student <Icon name="chat"/></button><div className="moderation-links"><button onClick={() => reportOrBlock('report')}>Report</button><button onClick={() => reportOrBlock('block')}>Block</button></div></section></div>
}

function ChatsPage({ targetUserId, user, setChatTarget, setError }: { targetUserId: string | null; user: User; setChatTarget: (id: string | null) => void; setError: (message: string) => void }) {
  const [chats, setChats] = useState<any[]>([])
  const [friends, setFriends] = useState<any[]>([])
  const [showFriends, setShowFriends] = useState(false)
  const [active, setActive] = useState<any>(null)
  const [messages, setMessages] = useState<any[]>([])
  const [body, setBody] = useState('')
  const [loading, setLoading] = useState(true)
  const [actionsOpen, setActionsOpen] = useState(false)
  const messagesEnd = useRef<HTMLDivElement>(null)
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api('/api/chats'); setChats(data.chats)
      if (targetUserId) { const conversation = await api(`/api/chats/with/${targetUserId}`); setActive(conversation); setMessages(conversation.messages) }
      else { setActive(null); setMessages([]) }
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not load chats') }
    finally { setLoading(false) }
  }, [targetUserId, setError])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (showFriends) api('/api/friends').then((data) => setFriends(data.friends)).catch((failure) => setError(failure instanceof Error ? failure.message : 'Could not load friends')) }, [showFriends, setError])
  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])
  const selectChat = async (chat: any) => { setChatTarget(chat.other_user.id); setActive(chat); try { const detail = await api(`/api/chats/${chat.id}`); setMessages(detail.messages) } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not open chat') } }
  const selectFriend = async (friend: any) => { setChatTarget(friend.id); setShowFriends(false); try { const detail = await api(`/api/chats/with/${friend.id}`); setActive(detail); setMessages(detail.messages) } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not open chat') } }
  const moderate = async (action: 'report' | 'block') => {
    const otherId = active?.other_user?.id
    if (!otherId) return
    try {
      if (action === 'report') { await api('/api/reports', json({ user_id: otherId, category: 'chat_report', details: '' })); setError('Your report was sent for review.') }
      else { await api('/api/blocks', json({ user_id: otherId })); setError('Student blocked. Their listings and messages are hidden from you.'); setActive(null); setChatTarget(null); setMessages([]); await load() }
    } catch (failure) { setError(failure instanceof Error ? failure.message : `Could not ${action} this student`) }
    setActionsOpen(false)
  }
  const send = async (event: FormEvent) => {
    event.preventDefault(); if (!body.trim() || !active?.other_user?.id) return
    try { const result = await api(`/api/chats/with/${active.other_user.id}/messages${active.exchange_id ? `?exchange_id=${active.exchange_id}` : ''}`, json({ body })); setMessages((previous) => [...previous, result.message]); setBody(''); setActive((previous: any) => ({ ...previous, id: result.chat_id })); const data = await api('/api/chats'); setChats(data.chats) }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not send message') }
  }
  if (active) return <div className="chat-screen"><div className="chat-top"><button className="icon-button" onClick={() => { setChatTarget(null); setActive(null); setActionsOpen(false) }}><Icon name="back"/></button><Avatar name={active.other_user?.full_name || 'Student'} size="sm"/><span><strong>{active.other_user?.full_name || 'Student'}</strong><small>{active.exchange_id ? 'Exchange chat' : active.other_user?.college || 'ONPay chat'}</small></span><button className="more-button" aria-label="Chat safety actions" onClick={() => setActionsOpen((open) => !open)}>•••</button></div>{actionsOpen && <div className="chat-safety-actions"><button onClick={() => moderate('report')}>Report student</button><button onClick={() => moderate('block')}>Block student</button></div>}<div className="chat-messages">{messages.length ? messages.map((message: any) => <div key={message.id} className={`message-bubble ${message.sender_id === user.id ? 'mine' : ''}`}>{message.body}<small>{new Date(message.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</small></div>) : <EmptyState icon="chat" title="Start a conversation" body="Keep exchange arrangements in ONPay chat. Never share your UPI PIN."/>}<div ref={messagesEnd}/></div><form className="chat-composer" onSubmit={send}><input value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} placeholder="Type a message…"/><button className="send-button" disabled={!body.trim()} aria-label="Send message"><Icon name="arrow"/></button></form></div>
  return <div className="page-stack"><PageTitle title="Chats" subtitle="Coordinate an exchange before meeting."/><div className="segmented small-tabs"><button className={!showFriends ? 'selected' : ''} onClick={() => setShowFriends(false)}>Conversations</button><button className={showFriends ? 'selected' : ''} onClick={() => setShowFriends(true)}>Friends</button></div>{loading ? <div className="loading-inline"><span className="spinner"/>Loading {showFriends ? 'friends' : 'chats'}…</div> : showFriends ? friends.length ? <div className="chat-list">{friends.map((friend) => <button className="chat-row" key={friend.id} onClick={() => selectFriend(friend)}><Avatar name={friend.full_name}/><span><strong>{friend.full_name}</strong><small>{friend.college || 'Verified exchange friend'}</small></span><small className="chat-date">Message</small></button>)}</div> : <EmptyState icon="user" title="No friends yet" body="Students are added after an exchange has been independently verified."/> : chats.length ? <div className="chat-list">{chats.map((chat) => <button className="chat-row" key={chat.id} onClick={() => selectChat(chat)}><Avatar name={chat.other_user.full_name}/><span><strong>{chat.other_user.full_name}</strong><small>{chat.last_message}</small></span><small className="chat-date">{new Date(chat.updated_at).toLocaleDateString()}</small></button>)}</div> : <EmptyState icon="chat" title="No conversations yet" body="Open a student listing to start a chat. Your messages are visible only to the participants."/>}</div>
}

function ScannerPage({ user, exchangesAction, navigate, payment, setPayment, setError }: { user: User; exchangesAction: (exchange: Exchange) => void; navigate: (screen: Screen) => void; payment: Payment | null; setPayment: (payment: Payment | null) => void; setError: (message: string) => void }) {
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [exchangeId, setExchangeId] = useState('')
  const [qrText, setQrText] = useState('')
  const [payee, setPayee] = useState<{ upi: string; name: string; amountPaise?: number; currency: 'INR' } | null>(null)
  const [cameraError, setCameraError] = useState('')
  const [cameraLoading, setCameraLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [choosing, setChoosing] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const scannerRef = useRef<BrowserQRCodeReaderType | null>(null)
  const controlsRef = useRef<IScannerControls | null>(null)
  const cameraGeneration = useRef(0)
  useEffect(() => { api('/api/exchanges').then((data) => { const available = data.exchanges.filter((exchange: Exchange) => exchange.status === 'meetup_confirmed' && exchange.requester_arrived && exchange.provider_arrived); setExchanges(available); if (available.length === 1) setExchangeId(available[0].id) }).catch(() => setExchanges([])) }, [])
  const stopCamera = () => {
    controlsRef.current?.stop()
    controlsRef.current = null
    const video = videoRef.current
    const stream = video?.srcObject as MediaStream | null
    stream?.getTracks().forEach((track) => track.stop())
    if (video) video.srcObject = null
  }
  useEffect(() => () => stopCamera(), [])
  const parse = (value: string) => {
    try {
      const result = parseUpiPayload(value)
      setPayee({ upi: result.upi, name: result.name, amountPaise: result.amountPaise, currency: result.currency })
      setError('')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not read this QR code.') }
  }
  const getScanner = async () => {
    if (!scannerRef.current) {
      const { BrowserQRCodeReader } = await import('@zxing/browser')
      scannerRef.current = new BrowserQRCodeReader(undefined, { delayBetweenScanAttempts: 200, delayBetweenScanSuccess: 800 })
    }
    return scannerRef.current
  }
  const startCamera = async () => {
    const generation = ++cameraGeneration.current
    setCameraError('')
    if (!window.isSecureContext) { setCameraError('Camera access requires HTTPS or localhost. Open ONPay on a secure connection.'); return }
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access is unavailable in this browser. Use HTTPS or localhost, or choose a QR image.')
      if (controlsRef.current) return
      setCameraLoading(true)
      const scanner = await getScanner()
      if (generation !== cameraGeneration.current) return
      let foundCode = false
      const controls = await scanner.decodeFromVideoDevice(undefined, videoRef.current || undefined, (result, _error, callbackControls) => {
        if (generation !== cameraGeneration.current) { callbackControls.stop(); return }
        if (!result || foundCode) return
        foundCode = true
        const value = result.getText()
        setQrText(value)
        parse(value)
        callbackControls.stop()
        controlsRef.current = null
        if (videoRef.current) videoRef.current.srcObject = null
        setScanning(false)
      })
      if (generation !== cameraGeneration.current) { controls.stop(); return }
      controlsRef.current = controls
      setScanning(!foundCode)
    } catch (failure) {
      if (generation !== cameraGeneration.current) return
      setScanning(false)
      const name = (failure as DOMException)?.name
      setCameraError(name === 'NotAllowedError' || name === 'SecurityError'
        ? 'Camera permission was denied. Enable camera access in this site’s browser settings, or use a QR image or manual UPI ID.'
        : name === 'NotFoundError' ? 'No camera was found. Choose a QR image or enter the UPI ID manually.'
          : failure instanceof Error ? failure.message : 'Could not open the camera.')
    }
    finally { if (generation === cameraGeneration.current) setCameraLoading(false) }
  }
  useEffect(() => {
    const timer = window.setTimeout(() => { void startCamera() }, 0)
    return () => { window.clearTimeout(timer); cameraGeneration.current += 1; stopCamera() }
  }, [])
  const importImage = async (file?: File) => {
    if (!file) return
    try {
      const scanner = await getScanner()
      const imageUrl = URL.createObjectURL(file)
      try {
        const result = await scanner.decodeFromImageUrl(imageUrl)
        setQrText(result.getText())
        parse(result.getText())
      } finally { URL.revokeObjectURL(imageUrl) }
    } catch { setError('No readable QR code was found in that image. Use a clear UPI QR, or enter the UPI ID manually.') }
  }
  const selected = exchanges.find((exchange) => exchange.id === exchangeId)
  const amountMismatch = !!(payee?.amountPaise !== undefined && selected && payee.amountPaise !== selected.amount)
  const initiate = async () => {
    if (!selected || !payee || amountMismatch) return
    setBusy(true); setError('')
    try {
      const result = await api('/api/payments/upi-intent', json({ exchange_id: selected.id, payee_upi: payee.upi }))
      setPayment(result.payment); exchangesAction(selected); setChoosing(true)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not prepare payment') }
    finally { setBusy(false) }
  }
  if (payment) return <PaymentPage payment={payment} setPayment={setPayment} navigate={navigate}/>
  return <div className="page-stack scanner-page"><PageTitle title="Scan UPI QR" subtitle="Review the payee and amount before opening a UPI app."/>
    <label className="field-label">Exchange<select className="select-control" value={exchangeId} onChange={(e) => { setExchangeId(e.target.value); setPayee(null) }}><option value="">Choose a confirmed meetup</option>{exchanges.filter((item) => item.requester_arrived && item.provider_arrived).map((exchange) => <option key={exchange.id} value={exchange.id}>{exchange.other_user?.full_name} · {money(exchange.amount)}</option>)}</select></label>
    {!exchanges.length && <div className="inline-callout"><Icon name="info" size={17}/> Confirm both meetup arrivals before initiating a payment.</div>}
    <div className="scanner-preview"><video ref={videoRef} className="scanner-video" muted playsInline/><div className="scan-frame"><i/><i/><i/><i/></div><span className="scan-caption">{cameraLoading ? 'Opening camera…' : scanning ? 'Align a UPI QR inside the frame' : 'Camera scan is ready'}</span></div>
    <div className="scanner-actions"><button className="button button-soft" onClick={startCamera} disabled={cameraLoading || scanning}><Icon name="qr" size={18}/>{cameraLoading ? 'Opening camera…' : scanning ? 'Scanning…' : 'Open camera'}</button><label className="button button-soft file-choice">Choose image<input type="file" accept="image/*" onChange={(e) => { void importImage(e.target.files?.[0]); e.currentTarget.value = '' }}/></label></div>
    {cameraError && <p className="inline-error">{cameraError}</p>}
    <label className="field-label">Or enter UPI ID / paste QR text<div className="manual-upi"><input value={qrText} onChange={(e) => { setQrText(e.target.value); setPayee(null) }} placeholder="name@bank"/><button className="button button-soft" type="button" onClick={() => parse(qrText)}>Review</button></div></label>
    {payee && <section className="panel review-panel"><div className="review-header"><span className="review-check"><Icon name="check"/></span><div><strong>Review payment</strong><small>QR contents are not proof of payment</small></div></div><div className="detail-row"><span>Payee name</span><strong>{payee.name}</strong></div><div className="detail-row"><span>UPI ID</span><strong>{payee.upi}</strong></div><div className="detail-row"><span>Amount</span><strong>{payee.amountPaise !== undefined ? money(payee.amountPaise) : selected ? money(selected.amount) : 'Set by exchange'} {payee.currency}</strong></div>{amountMismatch && <p className="inline-error">The QR fixes a different amount from this exchange. ONPay will not change or override the QR amount.</p>}<button className="button button-primary button-wide" disabled={!selected || amountMismatch || busy} onClick={() => setChoosing(true)}>Choose how to pay <Icon name="arrow"/></button></section>}
    <div className="payment-safety"><Icon name="shield" size={18}/><span>ONPay never asks for your UPI PIN. Payment status stays pending until verified independently.</span></div>
    {choosing && !payment && <div className="sheet-backdrop" onClick={() => setChoosing(false)}><section className="bottom-sheet" onClick={(e) => e.stopPropagation()}><div className="sheet-handle"/><h2>Pay via</h2><p>Your device will open its installed UPI app chooser. ONPay will not see your PIN.</p><div className="payee-summary"><Avatar name={payee?.name || ''}/><span><strong>{payee?.name}</strong><small>{payee?.upi}</small></span><b>{selected ? money(selected.amount) : ''}</b></div><button className="button button-primary button-wide" onClick={initiate} disabled={!selected || !payee || amountMismatch || busy}>{busy ? 'Preparing…' : 'Continue to UPI app'} <Icon name="arrow"/></button><button className="sheet-cancel" onClick={() => setChoosing(false)}>Cancel</button></section></div>}
  </div>
}

function PaymentPage({ payment, setPayment, navigate }: { payment: Payment; setPayment: (payment: Payment | null) => void; navigate: (screen: Screen) => void }) {
  const [paymentStatus, setPaymentStatus] = useState(payment.status)
  const [loading, setLoading] = useState(false)
  const [launchMessage, setLaunchMessage] = useState('')
  const launchUpiApp = () => {
    setLaunchMessage('Trying to open an installed UPI app…')
    window.setTimeout(() => {
      if (document.visibilityState === 'visible') setLaunchMessage('No UPI app opened. Install a compatible UPI app, try another app, or return here; the payment remains pending.')
    }, 1800)
  }
  const refresh = async () => {
    setLoading(true)
    try {
      if (paymentStatus === 'payment_initiated') await api(`/api/payments/${payment.id}/returned`, { method: 'POST' })
      const result = await api(`/api/payments/${payment.id}`)
      setPaymentStatus(result.payment.status); setPayment({ ...payment, status: result.payment.status })
    } catch { if (paymentStatus !== 'success') setPaymentStatus('verification_pending') }
    finally { setLoading(false) }
  }
  const success = paymentStatus === 'success'
  const pending = paymentStatus === 'verification_pending'
  const failed = paymentStatus === 'failed'
  return <div className="page-stack payment-page"><button className="back-link" onClick={() => navigate('transactions')}><Icon name="back" size={17}/> Transactions</button><section className="payment-status-card"><div className={`status-illustration ${pending ? 'pending' : success ? 'success' : ''}`}><Icon name={success ? 'check' : pending ? 'clock' : 'qr'} size={32}/></div><span className="eyebrow">{success ? 'PAYMENT VERIFIED' : failed ? 'PAYMENT FAILED' : pending ? 'VERIFICATION PENDING' : 'PAYMENT INITIATED'}</span><h1>{money(payment.amount)}</h1><p>{success ? 'This payment was independently reconciled.' : failed ? 'This attempt was marked failed by a configured provider.' : pending ? 'We have not verified that the payment reached the recipient.' : 'Complete the payment in your UPI app, then return here.'}</p><div className="reference-block"><small>ONPay reference</small><strong>{payment.reference}</strong></div>{paymentStatus === 'payment_initiated' && <a className="button button-primary button-wide" href={payment.upi_uri} onClick={launchUpiApp}>Open UPI app <Icon name="arrow"/></a>}{launchMessage && <p className="inline-error" role="status">{launchMessage}</p>}{!success && <button className="button button-soft button-wide" onClick={refresh} disabled={loading}>{loading ? 'Checking…' : paymentStatus === 'payment_initiated' ? 'I’m back in ONPay' : 'Refresh status'}</button>}{success && <button className="button button-primary button-wide" onClick={() => { setPayment(null); navigate('meetup') }}>View exchange <Icon name="arrow"/></button>}<div className="inline-callout"><Icon name="info" size={17}/>{payment.verification_note || 'Returning from a payment app does not verify settlement.'}</div></section>{!success && <button className="text-action centered" onClick={() => { setPayment(null); navigate('meetup') }}>View meetup details <Icon name="arrow" size={15}/></button>}</div>
}

function TransactionsPage({ navigate, setSelectedExchange }: { navigate: (screen: Screen) => void; setSelectedExchange: (exchange: Exchange) => void }) {
  const [filter, setFilter] = useState('all')
  const [items, setItems] = useState<Exchange[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [nextOffset, setNextOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  useEffect(() => {
    let alive = true
    setLoading(true); setNextOffset(0); setHasMore(false)
    api(`/api/transactions?status_filter=${filter}&offset=0&limit=30`).then((data) => { if (alive) { setItems(data.transactions); setNextOffset(data.next_offset); setHasMore(data.has_more) } }).catch(() => { if (alive) setItems([]) }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [filter])
  const loadMore = async () => { setLoadingMore(true); try { const data = await api(`/api/transactions?status_filter=${filter}&offset=${nextOffset}&limit=30`); setItems((current) => [...current, ...data.transactions]); setNextOffset(data.next_offset); setHasMore(data.has_more) } catch { /* keep the transactions already loaded */ } finally { setLoadingMore(false) } }
  const open = (exchange: Exchange) => { setSelectedExchange(exchange); navigate('meetup') }
  return <div className="page-stack"><PageTitle title="Transactions" subtitle="A record of exchanges and their separate payment states."/><div className="filter-row status-filters">{[['all', 'All'], ['success', 'Success'], ['in_transit', 'In transit'], ['failed', 'Failed']].map(([key, label]) => <button key={key} className={`filter-chip ${filter === key ? 'selected' : ''}`} onClick={() => setFilter(key)}>{label}</button>)}</div>
    {loading ? <div className="loading-inline"><span className="spinner"/>Loading activity…</div> : items.length ? <><div className="transaction-list">{items.map((item) => <button key={item.id} className="transaction-row" onClick={() => open(item)}><Avatar name={item.other_user?.full_name || 'Student'} size="sm"/><span className="transaction-info"><strong>{item.other_user?.full_name || 'Student'}</strong><small>{new Date(item.created_at || Date.now()).toLocaleDateString()} · Ref {item.id.slice(0, 8).toUpperCase()}</small><small className="transaction-state"><span className={`state-dot ${item.status}`}/>{item.status.replaceAll('_', ' ')}</small></span><span className="transaction-amount"><b>{money(item.amount)}</b><Icon name="arrow" size={17}/></span></button>)}</div>{hasMore && <button className="button button-soft button-wide" disabled={loadingMore} onClick={loadMore}>{loadingMore ? 'Loading…' : 'Load more transactions'}</button>}</> : <EmptyState icon="receipt" title="No transactions yet" body="When you match with a student, the exchange and its verification status will be listed here." action={<button className="button button-soft" onClick={() => navigate('matches')}>Find a match</button>}/>}</div>
}

function MeetupPage({ user, selected, setSelected, navigate, setError }: { user: User; selected: Exchange | null; setSelected: (exchange: Exchange) => void; navigate: (screen: Screen) => void; setError: (message: string) => void }) {
  const [items, setItems] = useState<Exchange[]>([])
  const [detail, setDetail] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const load = useCallback(async () => {
    try {
      const data = await api('/api/exchanges'); setItems(data.exchanges)
      const active = selected ? data.exchanges.find((item: Exchange) => item.id === selected.id) : data.exchanges[0]
      if (active) {
        if (!selected || selected.id !== active.id || selected.status !== active.status || selected.requester_arrived !== active.requester_arrived || selected.provider_arrived !== active.provider_arrived || selected.requester_cash_confirmed !== active.requester_cash_confirmed || selected.provider_cash_confirmed !== active.provider_cash_confirmed) setSelected(active)
        setDetail(await api(`/api/exchanges/${active.id}`))
      }
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not load exchange') }
  }, [selected, setError, setSelected])
  useEffect(() => { load() }, [load])
  const update = async (path: string, options: RequestInit, message?: string) => {
    if (!selected) return
    setBusy(true); setError('')
    try { const result = await api(path, options); if (result.exchange) setSelected(result.exchange); await load(); if (message) setError(message) }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not update exchange') }
    finally { setBusy(false) }
  }
  if (!selected && items.length === 0) return <div className="page-stack"><PageTitle title="Meet & exchange"/><EmptyState icon="pin" title="No meetup to show" body="Accept a compatible listing to coordinate a meetup." action={<button className="button button-primary" onClick={() => navigate('matches')}>Browse matches</button>}/></div>
  const exchange = selected || items[0]
  const requester = user.id === exchange.requester_id
  const arrived = requester ? exchange.requester_arrived : exchange.provider_arrived
  const cashDone = requester ? exchange.requester_cash_confirmed : exchange.provider_cash_confirmed
  const bothArrived = exchange.requester_arrived && exchange.provider_arrived
  const bothCash = exchange.requester_cash_confirmed && exchange.provider_cash_confirmed
  return <div className="page-stack"><button className="back-link" onClick={() => navigate('transactions')}><Icon name="back" size={17}/> Transactions</button><PageTitle title="Meet & exchange" subtitle="Confirm arrival separately from payment and cash handover."/>
    {items.length > 1 && <label className="field-label">Choose exchange<select className="select-control" value={exchange.id} onChange={(e) => { const next = items.find((item) => item.id === e.target.value); if (next) { setSelected(next); api(`/api/exchanges/${next.id}`).then(setDetail) } }}>{items.map((item) => <option key={item.id} value={item.id}>{item.other_user?.full_name} · {money(item.amount)}</option>)}</select></label>}
    <section className="meetup-card panel"><div className="meetup-person"><Avatar name={exchange.other_user?.full_name || 'Student'} size="lg"/><div><strong>{exchange.other_user?.full_name || 'Student'}</strong><small>{exchange.other_user?.college || 'Student'}</small></div><span className="status-pill neutral">{exchange.status.replaceAll('_', ' ')}</span></div>
      <div className="amount-summary"><small>Agreed exchange</small><strong>{money(exchange.amount)}</strong><p>Cash handover and UPI payment are tracked as separate actions.</p></div>
      <div className="detail-row"><span><Icon name="pin" size={16}/> Meeting location</span><strong>{exchange.location}</strong></div><div className="detail-row"><span><Icon name="clock" size={16}/> Preferred time</span><strong>{exchange.meetup_at}</strong></div>
      <a className="map-link" href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(exchange.location)}`} target="_blank" rel="noreferrer">Open directions <Icon name="arrow" size={15}/></a>
      <div className="confirm-step"><span className={`step-icon ${arrived ? 'done' : ''}`}><Icon name={arrived ? 'check' : 'pin'} size={18}/></span><div><strong>Confirm you’ve arrived</strong><small>{bothArrived ? 'Both participants confirmed arrival.' : 'This only confirms your meetup arrival.'}</small></div><button className={`button ${arrived ? 'button-soft' : 'button-primary'}`} disabled={busy || arrived || ['cancelled', 'disputed'].includes(exchange.status)} onClick={() => update(`/api/exchanges/${exchange.id}/arrival`, patch({ arrived: true }))}>{arrived ? 'Confirmed' : 'I’ve arrived'}</button></div>
      {bothArrived && <div className="confirm-step"><span className={`step-icon ${cashDone ? 'done' : ''}`}><Icon name={cashDone ? 'check' : 'receipt'} size={18}/></span><div><strong>Cash handover</strong><small>{bothCash ? 'Both participants confirmed the cash handover.' : 'Confirm only after the physical cash is exchanged.'}</small></div><button className={`button ${cashDone ? 'button-soft' : 'button-green'}`} disabled={busy || cashDone || exchange.status === 'disputed'} onClick={() => update(`/api/exchanges/${exchange.id}/cash-confirmation`, patch({ handed_over: true }))}>{cashDone ? 'Recorded' : 'Confirm cash'}</button></div>}
      {requester && bothArrived && <button className="button button-primary button-wide" onClick={() => navigate('scan')}><Icon name="qr"/> Scan UPI QR to pay</button>}
      <div className="payment-disclaimer"><Icon name="info" size={17}/><span>Payment verification is pending until independently checked. Returning from a UPI app does not mean it succeeded.</span></div>
      {detail?.payments?.map((item: any) => <div className="payment-history-item" key={item.id}><span>{item.reference}</span><b>{item.status.replaceAll('_', ' ')}</b><small>{money(item.amount)}</small></div>)}
      {exchange.status === 'awaiting_meetup' || exchange.status === 'meetup_confirmed' ? <button className="text-action cancel-action" onClick={() => update(`/api/exchanges/${exchange.id}/cancel`, { method: 'POST' })}>Cancel exchange</button> : null}
      {showReport ? <div className="report-box"><textarea id="dispute-details" rows={3} placeholder="Describe what happened…"/><button className="button button-primary" onClick={() => update(`/api/exchanges/${exchange.id}/dispute`, json({ user_id: exchange.other_user.id, category: 'exchange_dispute', details: (document.querySelector('#dispute-details') as HTMLTextAreaElement)?.value || '' }), 'Your dispute was sent for review.')}>Submit dispute</button></div> : <button className="text-action cancel-action" onClick={() => setShowReport(true)}>Report a problem or dispute</button>}
    </section>
    <section className="timeline"><h2>Status history</h2>{detail?.events?.length ? detail.events.map((event: any, index: number) => <div className="timeline-item" key={`${event.status}-${index}`}><span className="timeline-dot"/><div><strong>{event.status.replaceAll('_', ' ')}</strong><small>{event.details}</small></div><time>{new Date(event.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</time></div>) : <p className="quiet-empty">Status updates will appear here.</p>}</section>
  </div>
}

function NotificationsPage({ onRead }: { onRead: () => void }) {
  const [data, setData] = useState<any>({ notifications: [], unread_count: 0 })
  useEffect(() => { api('/api/notifications').then(setData).catch(() => setData({ notifications: [], unread_count: 0 })) }, [])
  const markRead = async (id: string) => { await api(`/api/notifications/${id}/read`, patch({})); setData((current: any) => ({ ...current, notifications: current.notifications.map((item: any) => item.id === id ? { ...item, read_at: new Date().toISOString() } : item), unread_count: Math.max(0, current.unread_count - 1) })); onRead() }
  return <div className="page-stack"><PageTitle title="Notifications" subtitle={`${data.unread_count} unread`}/>{data.notifications.length ? <div className="notification-list">{data.notifications.map((item: any) => <button key={item.id} className={`notification-row ${!item.read_at ? 'unread' : ''}`} onClick={() => !item.read_at && markRead(item.id)}><span className="notification-icon"><Icon name={item.kind === 'payment' ? 'receipt' : item.kind === 'message' ? 'chat' : 'info'}/></span><span><strong>{item.title}</strong><small>{item.body}</small><time>{new Date(item.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</time></span>{!item.read_at && <i/>}</button>)}</div> : <EmptyState icon="bell" title="All caught up" body="Match updates, messages, and payment status changes will appear here."/>}</div>
}

function ProfilePage({ user, setUser, navigate, signOut, setError }: { user: User; setUser: (user: User) => void; navigate: (screen: Screen) => void; signOut: () => void; setError: (message: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(user.full_name)
  const [college, setCollege] = useState(user.college || '')
  const save = async (event: FormEvent) => { event.preventDefault(); try { const result = await api('/api/profile', patch({ full_name: name, college })); setUser(result.user); setEditing(false) } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not update profile') } }
  return <div className="page-stack"><PageTitle title="Profile" subtitle="Your account, privacy, and exchange settings."/><section className="profile-card panel"><div className="profile-main"><Avatar name={user.full_name} size="lg"/><div><h2>{user.full_name}</h2><p>{user.college || 'College not added'}</p><span className="verified-label"><Icon name="shield" size={14}/>{user.verified_email || user.verified_phone ? 'Contact verified' : 'Contact not verified'}</span></div><button className="icon-button" onClick={() => setEditing((value) => !value)} aria-label="Edit profile"><Icon name="settings"/></button></div>{editing ? <form className="stack-form edit-profile" onSubmit={save}><label>Full name<input required value={name} onChange={(e) => setName(e.target.value)}/></label><label>College <span className="optional">(optional)</span><input value={college} onChange={(e) => setCollege(e.target.value)}/></label><button className="button button-primary">Save profile</button></form> : <div className="profile-contact"><span>{user.phone || user.email}</span><span className="status-pill neutral">Verified</span></div>}<div className="profile-stats"><div><b>{user.completed_exchanges}</b><small>Exchanges</small></div><div><b>{user.points}</b><small>Points</small></div><div><b>{user.friends_count}</b><small>Friends</small></div></div></section>
    <section className="menu-list"><MenuRow icon="receipt" title="Transactions" subtitle="Exchange and payment history" onClick={() => navigate('transactions')}/><MenuRow icon="heart" title="My friends" subtitle="People from verified exchanges" onClick={() => navigate('chats')}/><MenuRow icon="shield" title="Subscription plans" subtitle={`Current plan: ${user.plan.toUpperCase()}`} onClick={() => navigate('subscriptions')}/><MenuRow icon="star" title="Points & rewards" subtitle="View your points ledger" onClick={() => navigate('points')}/><MenuRow icon="pin" title="Location settings" subtitle="Choose a campus or meeting area" onClick={() => navigate('location')}/><MenuRow icon="info" title="Help & safety" subtitle="Support, reports, and meetup guidance" onClick={() => navigate('help')}/></section>
    <button className="button button-soft button-wide logout-button" onClick={signOut}>Log out</button><p className="account-note">ONPay does not hold funds or guarantee that a student has cash available.</p>
  </div>
}

function MenuRow({ icon, title, subtitle, onClick }: { icon: string; title: string; subtitle: string; onClick: () => void }) {
  return <button className="menu-row" onClick={onClick}><span className="menu-icon"><Icon name={icon}/></span><span><strong>{title}</strong><small>{subtitle}</small></span><Icon name="arrow" size={17}/></button>
}

function SubscriptionsPage() {
  const [data, setData] = useState<any>(null)
  useEffect(() => { api('/api/subscriptions').then(setData).catch(() => setData(null)) }, [])
  return <div className="page-stack"><PageTitle title="Plans" subtitle="Monthly allowances count completed, verified exchanges only."/>{data ? <><div className="plan-usage"><span>Current plan</span><strong>{data.current_plan === 'premium' ? 'PREMIUM' : data.current_plan.toUpperCase()}</strong><small>{data.remaining === null ? `${data.usage} completed this month · unlimited allowance` : `${data.usage} of ${data.limit} completed · ${data.reserved} active exchange(s) reserved · ${data.remaining} available this month`}</small></div><div className="plan-grid">{data.plans.map((plan: any) => <article className={`plan-card ${data.current_plan === plan.id ? 'current' : ''}`} key={plan.id}><span className="plan-name">{plan.name}{data.current_plan === plan.id && <small>Current</small>}</span><strong className="plan-price">₹{plan.price_inr}<small> / month</small></strong><span className="plan-limit">{plan.limit === null ? 'Unlimited completed exchanges' : `${plan.limit} completed exchanges / month`}</span>{plan.id !== 'free' && plan.id !== data.current_plan && <button className="button button-soft button-wide" disabled={!data.billing_configured} title="Subscription billing is not configured">{data.billing_configured ? 'Upgrade' : 'Billing unavailable'}</button>}</article>)}</div><div className="inline-callout"><Icon name="info" size={16}/>Plan prices are set to ₹199 for Plus and ₹499 for Premium. Billing is unavailable, so no paid plan can be activated.</div><p className="fine-print">Calendar-month allowances reset at midnight India time. Cancelled and failed exchanges do not use completed transaction allowance.</p></> : <EmptyState title="Plans unavailable" body="Could not load plan information."/>}</div>
}

function PointsPage() {
  const [data, setData] = useState<any>(null)
  useEffect(() => { api('/api/points').then(setData).catch(() => setData({ balance: 0, entries: [] })) }, [])
  return <div className="page-stack"><PageTitle title="Points & rewards" subtitle="Points are earned only after a verified exchange."/><div className="points-balance"><span className="points-spark">✦</span><small>Available points</small><strong>{data?.balance ?? '—'}</strong><p>Points are not cash and cannot be earned from failed or pending payments.</p></div>{data?.entries?.length ? <div className="ledger-list">{data.entries.map((entry: any, index: number) => <div key={index} className="ledger-row"><span><strong>{entry.reason.replaceAll('_', ' ')}</strong><small>{new Date(entry.created_at).toLocaleDateString()}</small></span><b>+{entry.amount}</b></div>)}</div> : <EmptyState icon="star" title="No points yet" body="Verified completed exchanges can award points. Attempts and pending payments do not count."/>}</div>
}

function LocationPage({ current, geoLabel, geoDetails, geoStatus, geoMessage, refreshLocation, save }: { current: string; geoLabel: string; geoDetails: ResolvedLocation | null; geoStatus: GeoStatus; geoMessage: string; refreshLocation: () => void; save: (label: string) => Promise<void> }) {
  const [label, setLabel] = useState(current)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  useEffect(() => setLabel(current), [current])
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true); setSaveMessage('')
    try {
      const selectedLocation = await saveManualLocation(label, save)
      setLabel(selectedLocation)
      setSaveMessage(selectedLocation ? 'Saved location updated.' : 'Saved location cleared.')
    } catch {
      setSaveMessage('Could not save your location. Please try again.')
    } finally { setSaving(false) }
  }
  const statusLabel = { checking: 'Checking permission', prompt: 'Permission not requested', loading: 'Finding your location', ready: 'Location available', denied: 'Permission denied', unavailable: 'Location unavailable', error: 'Location timed out', insecure: 'Secure connection required' }[geoStatus]
  const heading = geoLabel || (geoStatus === 'ready' ? 'Place name unavailable' : 'Detected location')
  return <div className="page-stack"><PageTitle title="Location settings" subtitle="Use your current area or choose a public campus location."/><section className="panel location-settings"><span className="location-large"><Icon name="pin" size={24}/></span><h2>{heading}</h2><p>{geoMessage || 'Location is requested only after you grant permission or choose Use current location. Coordinates are used for reverse geocoding and nearby matching; only an approximate point is stored with a listing.'}</p>
    {geoDetails && <dl className="location-details"><div><dt>Latitude</dt><dd>{geoDetails.latitude.toFixed(6)}°</dd></div><div><dt>Longitude</dt><dd>{geoDetails.longitude.toFixed(6)}°</dd></div><div><dt>Accuracy radius</dt><dd>±{Math.round(geoDetails.accuracy)} m</dd></div><div><dt>Last updated</dt><dd><time dateTime={new Date(geoDetails.timestamp).toISOString()}>{new Date(geoDetails.timestamp).toLocaleString()}</time></dd></div></dl>}
    {current && <div className="saved-location"><span>Saved campus or neighborhood</span><strong>{current}</strong></div>}
    <div className="permission-row"><span className={`permission-dot ${geoStatus === 'ready' ? 'granted' : geoStatus === 'denied' || geoStatus === 'insecure' ? 'denied' : 'unknown'}`}/><span><strong>{statusLabel}</strong><small>Browser location needs HTTPS or localhost and may be disabled in device settings.</small></span><button className="button button-soft" onClick={refreshLocation} disabled={geoStatus === 'loading'}>{geoStatus === 'loading' ? 'Finding…' : geoStatus === 'ready' ? 'Refresh' : geoStatus === 'denied' ? 'Try again' : 'Use current location'}</button></div>
    <form className="stack-form" onSubmit={submit}><label>Or enter campus or neighborhood<input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Aditya University" maxLength={180}/></label><button className="button button-primary button-wide" disabled={saving}>{saving ? 'Saving…' : 'Save manual location'}</button>{saveMessage && <p className={saveMessage.startsWith('Could not') ? 'inline-error' : 'location-saved-message'} role="status">{saveMessage}</p>}</form><p className="location-attribution">Place names are credited to the configured reverse-geocoding provider. Exact device coordinates are not saved to your profile.</p></section></div>
}

function HelpPage() {
  const [items, setItems] = useState<any[]>([])
  useEffect(() => { api('/api/help').then((data) => setItems(data.items)).catch(() => setItems([])) }, [])
  return <div className="page-stack"><PageTitle title="Help & safety" subtitle="Practical guidance for arranging a cash exchange."/><div className="safety-hero"><span><Icon name="shield" size={27}/></span><h2>Your safety comes first</h2><p>Take time to agree on a public place and clear terms before meeting.</p></div><div className="help-items">{items.map((item, index) => <details key={item.title} open={index === 0}><summary>{item.title}<span>＋</span></summary><p>{item.body}</p></details>)}</div><section className="panel support-card"><h3>Need help with an exchange?</h3><p>Open the exchange details and use “Report a problem or dispute” to record what happened.</p><div className="support-email"><Icon name="info" size={17}/> In-app reports are saved for your support team.</div></section><p className="fine-print">ONPay coordinates participants. It does not verify cash availability or guarantee payment settlement.</p></div>
}

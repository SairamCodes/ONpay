import { useState, type FormEvent } from 'react'
import type { OtpChannel, OtpRequestResult } from '../types'
import { isAcceptedOtpRequest } from '../utils'
import { api, json } from '../api'
import { Brand } from '../components/Brand'
import { Icon } from '../components/Icon'
import { Illustration } from '../components/Illustration'

export function AuthForm({
  intent,
  onOtp,
  onChangeIntent,
  busy,
  setError,
}: {
  intent: 'signup' | 'login'
  onOtp: (challenge: OtpRequestResult) => void
  onChangeIntent: (intent: 'signup' | 'login') => void
  busy: boolean
  setError: (message: string) => void
}) {
  const [channel, setChannel] = useState<OtpChannel>('mobile')
  const [name, setName] = useState('')
  const [contact, setContact] = useState('')
  const [college, setCollege] = useState('')
  const [agreed, setAgreed] = useState(true)
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (intent === 'signup' && !agreed) {
      setError('Please agree to the Terms and Privacy Policy to continue.')
      return
    }
    setSending(true)
    try {
      const result = await api<unknown>(
        '/api/auth/otp/request',
        json({ channel, contact, intent, ...(intent === 'signup' ? { full_name: name, college } : {}) })
      )
      if (!isAcceptedOtpRequest(result, channel, intent)) {
        throw new Error('The server did not confirm the verification request. Please try again later.')
      }
      setSent(true)
      onOtp({ ...result, channel, contact: contact.trim(), intent, full_name: name, college })
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not send a verification code.')
    } finally {
      setSending(false)
    }
  }

  return (
    <main className="auth-shell form-shell">
      <div className="auth-topline">
        <button className="icon-button" onClick={() => onChangeIntent('login')} aria-label="Back">
          <Icon name="back" />
        </button>
        <button
          className="link-button"
          onClick={() => onChangeIntent(intent === 'signup' ? 'login' : 'signup')}
        >
          {intent === 'signup' ? 'Log in' : 'Sign up'}
        </button>
      </div>
      <div className="auth-brand compact">
        <Brand />
        <span className="student-badge">
          <span>✦</span> Built for Students
        </span>
      </div>
      <section className="auth-card">
        <h1>{intent === 'signup' ? 'Create your account' : 'Welcome back'}</h1>
        <p className="muted">
          {intent === 'signup'
            ? 'Join ONPay and exchange cash easily.'
            : 'Log in securely with a one-time code.'}
        </p>
        <div className="segmented auth-tabs" role="tablist" aria-label="Verification method">
          <button
            type="button"
            className={channel === 'mobile' ? 'selected' : ''}
            onClick={() => setChannel('mobile')}
          >
            <Icon name="user" size={18} /> Mobile
          </button>
          <button
            type="button"
            className={channel === 'email' ? 'selected' : ''}
            onClick={() => setChannel('email')}
          >
            <Icon name="info" size={18} /> Email
          </button>
        </div>
        <form onSubmit={submit} className="stack-form">
          {intent === 'signup' && (
            <label>
              Full name
              <input
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter your full name"
                autoComplete="name"
              />
            </label>
          )}
          <label>
            {channel === 'mobile' ? 'Mobile number' : 'Email address'}
            <input
              required
              type={channel === 'mobile' ? 'tel' : 'email'}
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              placeholder={channel === 'mobile' ? '+91 98765 43210' : 'you@example.com'}
              autoComplete={channel === 'mobile' ? 'tel' : 'email'}
            />
          </label>
          {intent === 'signup' && (
            <label>
              College <span className="optional">(optional)</span>
              <input
                maxLength={140}
                value={college}
                onChange={(e) => setCollege(e.target.value)}
                placeholder="Enter your college or university"
              />
            </label>
          )}
          {intent === 'signup' && (
            <label className="check-row">
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
              />
              <span>
                I agree to ONPay’s{' '}
                <button
                  type="button"
                  className="inline-link"
                  onClick={() =>
                    setError(
                      'Terms and Privacy Policy: ONPay uses your verified contact for account access and stores the campus or meeting label you choose.'
                    )
                  }
                >
                  Terms
                </button>{' '}
                and{' '}
                <button
                  type="button"
                  className="inline-link"
                  onClick={() =>
                    setError(
                      'Privacy: when you allow location, ONPay sends coordinates to its API for nearby matching and reverse geocoding. New listings store only a rounded approximate point; exact coordinates are never returned to other students.'
                    )
                  }
                >
                  Privacy Policy
                </button>
                .
              </span>
            </label>
          )}
          <button className="button button-primary button-wide" disabled={busy || sending}>
            {busy || sending ? 'Sending code…' : sent ? 'Send a new code' : 'Send OTP'}{' '}
            <Icon name="arrow" />
          </button>
        </form>
        <div className="safe-note">
          <Icon name="lock" size={16} /> Your one-time code stays private. Never share your UPI PIN.
        </div>
      </section>
      <Illustration />
      <p className="auth-switch">
        {intent === 'signup' ? 'Already have an account?' : 'New to ONPay?'}{' '}
        <button
          className="link-button"
          onClick={() => onChangeIntent(intent === 'signup' ? 'login' : 'signup')}
        >
          {intent === 'signup' ? 'Log in' : 'Create account'}
        </button>
      </p>
    </main>
  )
}

export default AuthForm

import { useEffect, useState, type FormEvent } from 'react'
import type { OtpRequestResult } from '../types'
import { isAcceptedOtpRequest } from '../utils'
import { api, json } from '../api'
import { Brand } from '../components/Brand'
import { Icon } from '../components/Icon'

export function VerifyScreen({
  challenge,
  onBack,
  onSuccess,
  onChallenge,
  setError,
}: {
  challenge: OtpRequestResult | any
  onBack: () => void
  onSuccess: () => Promise<void>
  onChallenge: (challenge: any) => void
  setError: (message: string) => void
}) {
  const [code, setCode] = useState(challenge?.development_code || '')
  const [busy, setBusy] = useState(false)
  const [resending, setResending] = useState(false)
  const [resendIn, setResendIn] = useState(challenge?.resend_in_seconds || 0)

  useEffect(() => {
    setResendIn(challenge?.resend_in_seconds || 0)
    const timer = window.setInterval(
      () => setResendIn((seconds: number) => Math.max(0, seconds - 1)),
      1000
    )
    return () => window.clearInterval(timer)
  }, [challenge?.challenge_id, challenge?.resend_in_seconds])

  const verify = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      await api('/api/auth/otp/verify', json({ challenge_id: challenge.challenge_id, code }))
      await onSuccess()
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not verify that code.')
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    if (resendIn > 0 || resending) return
    setError('')
    setResending(true)
    try {
      const next = await api<unknown>(
        '/api/auth/otp/request',
        json({
          channel: challenge.channel,
          contact: challenge.contact,
          intent: challenge.intent,
          full_name: challenge.full_name,
          college: challenge.college,
        })
      )
      if (!isAcceptedOtpRequest(next, challenge.channel, challenge.intent)) {
        throw new Error('The server did not confirm the new verification request. Please try again later.')
      }
      const updated = {
        ...next,
        channel: challenge.channel,
        contact: challenge.contact,
        intent: challenge.intent,
        full_name: challenge.full_name,
        college: challenge.college,
      }
      onChallenge(updated)
      setCode(updated.development_code || '')
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not send a new code.')
    } finally {
      setResending(false)
    }
  }

  const contactLabel = challenge?.contact || 'your contact'

  return (
    <main className="auth-shell verify-shell">
      <button className="icon-button back-abs" onClick={onBack} aria-label="Back">
        <Icon name="back" />
      </button>
      <div className="verify-icon">
        <Icon name="lock" size={25} />
      </div>
      <Brand small />
      <h1>Verify your contact</h1>
      <p className="muted">
        If this contact can continue, a 6-digit code was sent to
        <br />
        <strong>{contactLabel}</strong>
      </p>
      {challenge?.development_code && (
        <div className="dev-code">
          <span>Local development code</span>
          <b>{challenge.development_code}</b>
        </div>
      )}
      <form onSubmit={verify} className="stack-form otp-form">
        <label>
          Verification code
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            pattern="[0-9]{6}"
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="••••••"
          />
        </label>
        <button className="button button-primary button-wide" disabled={busy}>
          {busy ? 'Verifying…' : 'Verify and continue'} <Icon name="arrow" />
        </button>
      </form>
      <p className="muted small-centered">The code expires in 5 minutes.</p>
      <button
        type="button"
        className="link-button resend-code"
        onClick={resend}
        disabled={resending || resendIn > 0}
      >
        {resending ? 'Sending a new code…' : resendIn > 0 ? `Resend available in ${resendIn}s` : 'Resend code'}
      </button>
    </main>
  )
}

export default VerifyScreen

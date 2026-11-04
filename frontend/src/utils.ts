import type { OtpChannel, OtpRequestResult } from './types'

export const money = (paise: number) =>
  `₹${Math.floor(paise / 100).toLocaleString('en-IN')}${paise % 100 ? `.${String(paise % 100).padStart(2, '0')}` : ''}`

export const initials = (name = '') =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase() || 'S'

export function isAcceptedOtpRequest(
  value: unknown,
  channel: OtpChannel,
  intent: 'signup' | 'login'
): value is OtpRequestResult {
  if (!value || typeof value !== 'object') return false
  const result = value as Record<string, unknown>
  return (
    result.accepted === true &&
    typeof result.challenge_id === 'string' &&
    result.challenge_id.length > 0 &&
    typeof result.expires_in_seconds === 'number' &&
    Number.isFinite(result.expires_in_seconds) &&
    typeof result.resend_in_seconds === 'number' &&
    Number.isFinite(result.resend_in_seconds) &&
    result.channel === channel &&
    typeof result.contact === 'string' &&
    result.intent === intent &&
    (result.development_code === undefined || typeof result.development_code === 'string')
  )
}

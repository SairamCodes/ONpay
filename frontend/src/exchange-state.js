const DISPLAYED_EXCHANGE_FIELDS = [
  'status',
  'payment_status',
  'requester_arrived',
  'provider_arrived',
  'requester_cash_confirmed',
  'provider_cash_confirmed',
]

// Replace a selected snapshot when server-owned state shown by the screen changes.
export function exchangeSnapshotChanged(current, latest) {
  if (!current || !latest || current.id !== latest.id) return true
  return DISPLAYED_EXCHANGE_FIELDS.some((field) => current[field] !== latest[field])
}

export async function refreshPaymentStatus(api, paymentId, currentStatus) {
  if (currentStatus === 'payment_initiated') {
    // A failed return acknowledgement does not prevent an authoritative status read.
    try { await api(`/api/payments/${paymentId}/returned`, { method: 'POST' }) } catch { /* GET below is authoritative. */ }
  }
  const result = await api(`/api/payments/${paymentId}`)
  if (typeof result?.payment?.status !== 'string') throw new Error('ONPay returned an invalid payment status.')
  return result.payment
}

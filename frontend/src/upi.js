const VPA_PATTERN = /^[A-Za-z0-9._-]{2,256}@[A-Za-z0-9.-]{2,64}$/

/** Parse a standard UPI payment URI or a manually entered UPI ID. */
export function parseUpiPayload(value) {
  const input = String(value ?? '').trim()
  if (VPA_PATTERN.test(input)) return { upi: input, name: 'UPI recipient', amountPaise: undefined, currency: 'INR' }
  if (!/^upi:\/\/pay\?/i.test(input)) throw new Error('Unsupported QR format. Use a UPI payment QR or enter a UPI ID.')

  let url
  try { url = new URL(input) } catch { throw new Error('This UPI payment QR is malformed.') }
  if (url.protocol.toLowerCase() !== 'upi:' || url.hostname.toLowerCase() !== 'pay') {
    throw new Error('Unsupported UPI QR format. Only UPI pay links can be used.')
  }
  for (const key of ['pa', 'pn', 'am', 'cu']) {
    if (url.searchParams.getAll(key).length > 1) throw new Error(`The UPI QR contains duplicate ${key.toUpperCase()} fields.`)
  }
  const upi = url.searchParams.get('pa')?.trim() || ''
  if (!VPA_PATTERN.test(upi)) throw new Error('The UPI QR does not contain a valid payee UPI ID.')
  const currency = (url.searchParams.get('cu') || 'INR').toUpperCase()
  if (currency !== 'INR') throw new Error(`This QR uses ${currency}; ONPay supports INR payments only.`)
  const amountText = url.searchParams.get('am')
  let amountPaise
  if (amountText !== null) {
    if (!/^\d{1,7}(?:\.\d{1,2})?$/.test(amountText)) throw new Error('The amount in this UPI QR is invalid.')
    const [rupees, paise = ''] = amountText.split('.')
    amountPaise = Number(rupees) * 100 + Number(paise.padEnd(2, '0'))
    if (!Number.isSafeInteger(amountPaise) || amountPaise <= 0) throw new Error('The amount in this UPI QR must be greater than zero.')
  }
  const name = (url.searchParams.get('pn') || 'UPI recipient').trim().slice(0, 100) || 'UPI recipient'
  return { upi, name, amountPaise, currency }
}

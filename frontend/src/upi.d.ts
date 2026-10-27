export type ParsedUpiPayload = {
  upi: string
  name: string
  amountPaise: number | undefined
  currency: 'INR'
}
export function parseUpiPayload(value: string): ParsedUpiPayload

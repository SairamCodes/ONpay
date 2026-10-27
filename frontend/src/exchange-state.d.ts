export type ExchangeSnapshot = {
  id: string
  status?: string
  payment_status?: string | null
  requester_arrived?: boolean
  provider_arrived?: boolean
  requester_cash_confirmed?: boolean
  provider_cash_confirmed?: boolean
}

export function exchangeSnapshotChanged(current: ExchangeSnapshot | null, latest: ExchangeSnapshot | null): boolean

export type PaymentStatusResult = { id: string; status: string; [key: string]: unknown }
export function refreshPaymentStatus(api: (path: string, options?: RequestInit) => Promise<any>, paymentId: string, currentStatus: string): Promise<PaymentStatusResult>

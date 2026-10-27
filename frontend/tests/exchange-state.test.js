import test from 'node:test'
import assert from 'node:assert/strict'
import { exchangeSnapshotChanged, refreshPaymentStatus } from '../src/exchange-state.js'

const exchange = (overrides = {}) => ({
  id: 'exchange-1',
  status: 'verification_pending',
  payment_status: 'verification_pending',
  requester_arrived: true,
  provider_arrived: true,
  requester_cash_confirmed: false,
  provider_cash_confirmed: false,
  ...overrides,
})

test('refreshes the selected exchange when the payment status changes', () => {
  assert.equal(exchangeSnapshotChanged(exchange(), exchange({ payment_status: 'receiver_confirmed' })), true)
})

test('keeps an unchanged selected exchange snapshot stable', () => {
  assert.equal(exchangeSnapshotChanged(exchange(), exchange()), false)
})

test('refreshes when identity or another visible state changes', () => {
  assert.equal(exchangeSnapshotChanged(exchange(), exchange({ id: 'exchange-2' })), true)
  assert.equal(exchangeSnapshotChanged(exchange(), exchange({ requester_cash_confirmed: true })), true)
})

test('uses the server status even if recording the app return fails', async () => {
  const requests = []
  const payment = await refreshPaymentStatus(async (path, options) => {
    requests.push([path, options?.method || 'GET'])
    if (options?.method === 'POST') throw new Error('return request failed')
    return { payment: { id: 'payment-1', status: 'payment_initiated' } }
  }, 'payment-1', 'payment_initiated')

  assert.deepEqual(payment, { id: 'payment-1', status: 'payment_initiated' })
  assert.deepEqual(requests, [['/api/payments/payment-1/returned', 'POST'], ['/api/payments/payment-1', 'GET']])
})

test('does not invent a pending state when the status endpoint fails', async () => {
  await assert.rejects(
    refreshPaymentStatus(async () => { throw new Error('server unavailable') }, 'payment-1', 'payment_initiated'),
    /server unavailable/,
  )
})

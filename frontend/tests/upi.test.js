import test from 'node:test'
import assert from 'node:assert/strict'
import { parseUpiPayload } from '../src/upi.js'

test('parses a standard UPI QR and keeps its fixed amount', () => {
  assert.deepEqual(parseUpiPayload('upi://pay?pa=recipient%40upi&pn=Recipient&am=500&cu=INR'), {
    upi: 'recipient@upi', name: 'Recipient', amountPaise: 50000, currency: 'INR',
  })
})

test('allows UPI QR without a fixed amount so exchange amount can be used', () => {
  assert.equal(parseUpiPayload('upi://pay?pa=recipient%40upi&pn=Recipient&cu=INR').amountPaise, undefined)
})

test('accepts a manual VPA', () => {
  assert.deepEqual(parseUpiPayload(' student.name@okaxis '), {
    upi: 'student.name@okaxis', name: 'UPI recipient', amountPaise: undefined, currency: 'INR',
  })
})

test('rejects malformed or unsupported QR values', () => {
  for (const value of ['not a QR', 'upi://collect?pa=a%40upi', 'upi://pay?pn=NoPayee']) {
    assert.throws(() => parseUpiPayload(value), Error)
  }
})

test('rejects invalid amounts, non-INR currency, and duplicate critical fields', () => {
  for (const value of [
    'upi://pay?pa=a%40upi&am=0',
    'upi://pay?pa=a%40upi&am=1.234',
    'upi://pay?pa=a%40upi&am=5&cu=USD',
    'upi://pay?pa=a%40upi&pa=b%40upi',
  ]) assert.throws(() => parseUpiPayload(value), Error)
})

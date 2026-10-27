import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveApiBase } from '../src/api-config.js'

test('uses localhost only for local development when no API URL is configured', () => {
  assert.equal(resolveApiBase(undefined, true), 'http://localhost:8000')
})

test('uses the current development host when the app is opened from another device or LAN address', () => {
  assert.equal(resolveApiBase(undefined, true, '192.168.1.40'), 'http://192.168.1.40:8000')
  assert.equal(resolveApiBase(undefined, true, '::1'), 'http://[::1]:8000')
})

test('does not silently route production traffic to localhost', () => {
  assert.equal(resolveApiBase(undefined, false), '')
})

test('uses the configured API origin and removes trailing slashes', () => {
  assert.equal(resolveApiBase(' https://api.onpay.example/ ', false), 'https://api.onpay.example')
})

import test from 'node:test'
import assert from 'node:assert/strict'
import { matchAndNavigate } from '../src/match-flow.js'

const exchange = { id: 'exchange-from-server', status: 'awaiting_meetup' }

test('uses the persisted exchange response and opens the meetup screen', async () => {
  const calls = []
  const actual = await matchAndNavigate(
    async (path, options) => {
      calls.push([path, options])
      return { exchange }
    },
    'listing-1',
    50000,
    (selected) => calls.push(['selected', selected]),
    (screen) => calls.push(['navigate', screen]),
    () => calls.push(['refresh']),
  )

  assert.equal(actual, exchange)
  assert.equal(calls[0][0], '/api/listings/listing-1/accept')
  assert.deepEqual(JSON.parse(calls[0][1].body), { amount: 50000 })
  assert.deepEqual(calls.slice(1), [
    ['selected', exchange],
    ['refresh'],
    ['navigate', 'meetup'],
  ])
})

test('does not navigate or invent an exchange when matching fails', async () => {
  const calls = []
  await assert.rejects(
    matchAndNavigate(
      async () => { throw new Error('Try matching again') },
      'listing-1',
      50000,
      (selected) => calls.push(['selected', selected]),
      (screen) => calls.push(['navigate', screen]),
      () => calls.push(['refresh']),
    ),
    /Try matching again/,
  )
  assert.deepEqual(calls, [])
})

test('does not navigate when the server response lacks an exchange', async () => {
  const calls = []
  await assert.rejects(
    matchAndNavigate(
      async () => ({}),
      'listing-1',
      50000,
      (selected) => calls.push(['selected', selected]),
      (screen) => calls.push(['navigate', screen]),
      () => calls.push(['refresh']),
    ),
    /could not confirm this match/,
  )
  assert.deepEqual(calls, [])
})

import test from 'node:test'
import assert from 'node:assert/strict'
import { fetchAvailableListings } from '../src/listing-feed.js'

test('Home and Activity share the active listing endpoint without a location filter', async () => {
  const requests = []
  const listings = [
    { id: 'request-active', status: 'active' },
    { id: 'request-matched', status: 'matched' },
    { id: 'request-cancelled', status: 'cancelled' },
  ]
  const available = await fetchAvailableListings(async (path) => {
    requests.push(path)
    return { listings }
  }, null)

  assert.deepEqual(requests, ['/api/listings'])
  assert.deepEqual(available, [listings[0]])
})

test('shared listing feed applies the same approximate-location query', async () => {
  const requests = []
  await fetchAvailableListings(async (path) => {
    requests.push(path)
    return { listings: [] }
  }, { latitude: 12.5, longitude: 77.6 })

  const query = new URL(requests[0], 'https://onpay.example').searchParams
  assert.equal(requests[0].split('?')[0], '/api/listings')
  assert.equal(query.get('latitude'), '12.5')
  assert.equal(query.get('longitude'), '77.6')
  assert.equal(query.get('radius_km'), '25')
})

test('listing feed surfaces invalid API response shapes instead of looking empty', async () => {
  await assert.rejects(
    fetchAvailableListings(async () => ({}), null),
    /invalid listings response/,
  )
})

test('empty feeds remain empty and rejected refreshes remain errors', async () => {
  const empty = await fetchAvailableListings(async () => ({ listings: [] }), null)
  assert.deepEqual(empty, [])

  await assert.rejects(
    fetchAvailableListings(async () => { throw new Error('network unavailable') }, null),
    /network unavailable/,
  )
})

test('repeating the feed request refreshes its data instead of retaining a stale snapshot', async () => {
  let version = 0
  const api = async () => ({ listings: [{ id: `request-${++version}`, status: 'active' }] })

  const first = await fetchAvailableListings(api, null)
  const refreshed = await fetchAvailableListings(api, null)
  assert.equal(first[0].id, 'request-1')
  assert.equal(refreshed[0].id, 'request-2')
})

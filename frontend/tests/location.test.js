import test from 'node:test'
import assert from 'node:assert/strict'
import { detectCurrentLocation, requestCurrentLocation, saveManualLocation } from '../src/location.js'

function geolocationSuccess({
  latitude = 12.9716,
  longitude = 77.5946,
  accuracy = 18,
  timestamp = 1_798_000_000_000,
} = {}) {
  return {
    getCurrentPosition(success, _failure, options) {
      assert.deepEqual(options, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 })
      success({ coords: { latitude, longitude, accuracy }, timestamp })
    },
  }
}

test('detects fresh browser coordinates and displays the provider place name', async () => {
  let queried
  const result = await detectCurrentLocation({
    geolocation: geolocationSuccess(),
    isSecureContext: true,
    hostname: 'onpay.example',
    reverseGeocode: async (details) => {
      queried = details
      return { status: 'resolved', label: 'Indiranagar, Karnataka', attribution: 'Configured geocoder' }
    },
  })

  assert.deepEqual(queried, {
    latitude: 12.9716,
    longitude: 77.5946,
    accuracy: 18,
    timestamp: 1_798_000_000_000,
  })
  assert.equal(result.placeName, 'Indiranagar, Karnataka')
  assert.equal(result.accuracy, 18)
  assert.match(result.message, /Configured geocoder/)
})

test('keeps coordinates visible when reverse geocoding fails without inventing a place', async () => {
  const result = await detectCurrentLocation({
    geolocation: geolocationSuccess(),
    isSecureContext: true,
    hostname: 'onpay.example',
    reverseGeocode: async () => { throw new Error('provider unavailable') },
  })

  assert.equal(result.latitude, 12.9716)
  assert.equal(result.longitude, 77.5946)
  assert.equal(result.placeName, '')
  assert.match(result.message, /place-name service could not be reached/)
})

test('reports permission denial and does not call reverse geocoding', async () => {
  let reverseCalled = false
  const geolocation = {
    getCurrentPosition(_success, failure) {
      failure({ code: 1 })
    },
  }

  await assert.rejects(
    detectCurrentLocation({
      geolocation,
      isSecureContext: true,
      hostname: 'onpay.example',
      reverseGeocode: async () => { reverseCalled = true; return { status: 'resolved', label: 'Not used' } },
    }),
    (error) => error.code === 'permission_denied' && /access was denied/.test(error.message),
  )
  assert.equal(reverseCalled, false)
})

test('explains insecure origins and still permits localhost', async () => {
  await assert.rejects(
    requestCurrentLocation({ geolocation: geolocationSuccess(), isSecureContext: false, hostname: 'onpay.example' }),
    (error) => error.code === 'insecure_origin' && /requires HTTPS/.test(error.message),
  )

  const position = await requestCurrentLocation({
    geolocation: geolocationSuccess(),
    isSecureContext: false,
    hostname: 'localhost',
  })
  assert.equal(position.latitude, 12.9716)
  const ipv6Position = await requestCurrentLocation({
    geolocation: geolocationSuccess(),
    isSecureContext: false,
    hostname: '[::1]',
  })
  assert.equal(ipv6Position.longitude, 77.5946)
})

test('reports geolocation timeouts and unavailable browser support', async () => {
  await assert.rejects(
    requestCurrentLocation({
      geolocation: { getCurrentPosition(_success, failure) { failure({ code: 3 }) } },
      isSecureContext: true,
      hostname: 'onpay.example',
    }),
    (error) => error.code === 'timeout' && /too long to respond/.test(error.message),
  )
  await assert.rejects(
    requestCurrentLocation({ geolocation: null, isSecureContext: true, hostname: 'onpay.example' }),
    (error) => error.code === 'unsupported' && /does not support location/.test(error.message),
  )
})

test('saves and returns the selected manual campus label', async () => {
  let persisted
  const selected = await saveManualLocation('  Aditya University  ', async (label) => {
    persisted = label
    return { stored_location: label }
  })
  assert.equal(persisted, 'Aditya University')
  assert.equal(selected, 'Aditya University')
})

function locationError(code, message) {
  const error = new Error(message)
  error.code = code
  return error
}

function isLocalhost(hostname) {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '[::1]'
}

export function requestCurrentLocation({
  geolocation = globalThis.navigator?.geolocation,
  isSecureContext = globalThis.isSecureContext,
  hostname = globalThis.location?.hostname || '',
} = {}) {
  if (!isSecureContext && !isLocalhost(hostname)) {
    return Promise.reject(locationError('insecure_origin', 'Location requires HTTPS or localhost. Open ONPay over a secure connection, or choose a campus manually.'))
  }
  if (!geolocation) {
    return Promise.reject(locationError('unsupported', 'This browser does not support location. Choose your campus manually.'))
  }

  return new Promise((resolve, reject) => {
    geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude, accuracy } = position.coords
        if (
          ![latitude, longitude, accuracy].every(Number.isFinite)
          || latitude < -90 || latitude > 90
          || longitude < -180 || longitude > 180
          || accuracy < 0
        ) {
          reject(locationError('unavailable', 'The device returned invalid location details. Try again or choose a campus manually.'))
          return
        }
        resolve({
          latitude,
          longitude,
          accuracy,
          timestamp: Number.isFinite(position.timestamp) && position.timestamp > 0
            ? position.timestamp
            : Date.now(),
        })
      },
      (error) => {
        if (error.code === 1) {
          reject(locationError('permission_denied', 'Location access was denied. Allow location in this site’s browser settings, or choose a campus manually.'))
        } else if (error.code === 3) {
          reject(locationError('timeout', 'Location took too long to respond. Try refreshing, or choose a campus manually.'))
        } else {
          reject(locationError('unavailable', 'Device location is unavailable. Check your device settings, or choose a campus manually.'))
        }
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )
  })
}

export async function detectCurrentLocation({ geolocation, reverseGeocode, isSecureContext, hostname } = {}) {
  const details = await requestCurrentLocation({ geolocation, isSecureContext, hostname })
  try {
    const result = await reverseGeocode(details)
    if (result?.status === 'resolved' && typeof result.label === 'string' && result.label.trim()) {
      return {
        ...details,
        placeName: result.label.trim(),
        message: `Place name from ${result.attribution || 'the configured location provider'}.`,
      }
    }
    if (result?.reason === 'missing_user_agent' || result?.reason === 'provider_not_configured') {
      return {
        ...details,
        placeName: '',
        message: result.reason === 'missing_user_agent'
          ? 'Coordinates detected, but reverse geocoding is not configured. Set the provider User-Agent in the backend settings.'
          : 'Coordinates detected, but no reverse-geocoding provider is configured on the server.',
      }
    }
    return {
      ...details,
      placeName: '',
      message: 'Coordinates detected, but reverse geocoding is unavailable or returned no place name. Try Refresh later or choose a campus manually.',
    }
  } catch {
    return {
      ...details,
      placeName: '',
      message: 'Coordinates detected, but the place-name service could not be reached. Try Refresh later or choose a campus manually.',
    }
  }
}

export async function saveManualLocation(label, save) {
  const selectedLocation = label.trim()
  await save(selectedLocation)
  return selectedLocation
}

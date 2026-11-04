export async function fetchAvailableListings(api, coordinates) {
  const query = new URLSearchParams()
  if (coordinates) {
    query.set('latitude', String(coordinates.latitude))
    query.set('longitude', String(coordinates.longitude))
    query.set('radius_km', '25')
  }
  const data = await api(`/api/listings${query.size ? `?${query}` : ''}`)
  if (!Array.isArray(data?.listings)) throw new Error('ONPay returned an invalid listings response.')
  return data.listings.filter((listing) => listing?.status === 'active')
}

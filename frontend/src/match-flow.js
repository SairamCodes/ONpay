export async function matchAndNavigate(api, listingId, amount, setSelectedExchange, navigate, refreshListings) {
  const result = await api(`/api/listings/${encodeURIComponent(listingId)}/accept`, {
    method: 'POST',
    body: JSON.stringify({ amount }),
  })
  const exchange = result?.exchange
  if (!exchange || typeof exchange.id !== 'string' || typeof exchange.status !== 'string') {
    throw new Error('ONPay could not confirm this match. Please try again.')
  }
  setSelectedExchange(exchange)
  refreshListings()
  navigate('meetup')
  return exchange
}

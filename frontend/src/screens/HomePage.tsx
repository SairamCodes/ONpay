import { useCallback, useEffect, useState } from 'react'
import type { Coordinates, Exchange, GeoStatus, Listing, Screen, User } from '../types'
import { money } from '../utils'
import { api } from '../api'
import { fetchAvailableListings } from '../listing-feed.js'
import { Avatar } from '../components/Avatar'
import { Icon } from '../components/Icon'
import { ListingCard } from '../components/ListingCard'
import { EmptyState } from '../components/EmptyState'
import { MatchRequestsPanel } from '../features/match-requests/MatchRequestsPanel'
import { SendMatchRequestModal } from '../features/match-requests/SendMatchRequestModal'

export function HomePage({
  user,
  locationLabel,
  geoLabel,
  geoStatus,
  geoMessage,
  coordinates,
  refreshLocation,
  navigate,
  setLocation,
  setSelectedListing,
  setSelectedExchange,
}: {
  user: User
  locationLabel: string
  geoLabel: string
  geoStatus: GeoStatus
  geoMessage: string
  coordinates: Coordinates | null
  refreshLocation: () => void
  navigate: (screen: Screen) => void
  setLocation: (label: string) => void
  setSelectedListing: (listing: Listing) => void
  setSelectedExchange: (exchange: Exchange) => void
}) {
  const [listings, setListings] = useState<Listing[]>([])
  const [mine, setMine] = useState<any[]>([])
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [retry, setRetry] = useState(0)
  const [requestListing, setRequestListing] = useState<Listing | null>(null)

  const load = useCallback(async () => {
    try {
      const [available, own, activity] = await Promise.all([
        fetchAvailableListings<Listing>(api, coordinates),
        api('/api/my-listings'),
        api('/api/exchanges'),
      ])
      setListings(available.slice(0, 3))
      setMine(own.listings.filter((item: any) => item.status !== 'cancelled'))
      setExchanges(activity.exchanges.slice(0, 3))
      setLoadError('')
    } catch (failure) {
      setLoadError(failure instanceof Error ? failure.message : 'Could not load your ONPay activity.')
    } finally {
      setLoading(false)
    }
  }, [coordinates, retry])

  useEffect(() => {
    load()
  }, [load])

  const useLocation = () => {
    if (geoStatus === 'loading' || geoStatus === 'checking') return
    if (geoStatus === 'denied' || geoStatus === 'unavailable') navigate('location')
    else refreshLocation()
  }

  const displayedArea = geoLabel || locationLabel

  return (
    <div className="page-stack">
      <section className="home-greeting">
        <div>
          <span className="eyebrow">WELCOME BACK</span>
          <h1>
            Hi, {user.full_name.split(' ')[0]} <span>👋</span>
          </h1>
          <p>What do you need today?</p>
        </div>
        <div className="home-points">
          <b>{user.points ?? user.total_points ?? 0}</b>
          <small>points</small>
        </div>
      </section>

      {/* Action Card Grid */}
      <div className="action-card-grid">
        <button className="action-card need" onClick={() => navigate('need')}>
          <div className="action-icon" style={{ margin: '0 auto' }}>
            <Icon name="arrow" />
          </div>
          <h3>I NEED CASH</h3>
          <p>Pay digitally, receive cash</p>
        </button>
        <button className="action-card have" onClick={() => navigate('have')}>
          <div className="action-icon" style={{ margin: '0 auto' }}>
            <Icon name="check" />
          </div>
          <h3>I HAVE CASH</h3>
          <p>Give cash, receive UPI</p>
        </button>
      </div>

      <button className={`campus-banner ${displayedArea ? 'has-location' : ''}`} onClick={useLocation}>
        <span className="campus-icon">
          {geoStatus === 'loading' || geoStatus === 'checking' ? (
            <span className="spinner small-spinner" />
          ) : (
            <Icon name="pin" />
          )}
        </span>
        <span>
          <strong>
            {displayedArea ||
              (geoStatus === 'loading' || geoStatus === 'checking'
                ? 'Finding your current area…'
                : geoStatus === 'denied'
                ? 'Location access is blocked'
                : 'Enable location for nearby matches')}
          </strong>
          <small>
            {geoMessage ||
              (coordinates
                ? 'Listings are filtered using your approximate current area.'
                : 'Location is optional; you can choose a campus manually.')}
          </small>
        </span>
        <span className="banner-action">
          {geoStatus === 'denied' || geoStatus === 'unavailable' ? 'Settings' : coordinates ? 'Refresh' : 'Enable'}{' '}
          <Icon name="arrow" size={16} />
        </span>
      </button>

      {/* Match Requests Panel */}
      <MatchRequestsPanel
        navigate={navigate}
        onSelectExchange={(ex) => {
          setSelectedExchange(ex)
          navigate('meetup')
        }}
      />

      {/* Nearby Users / Activity Section */}
      <section className="section-block">
        <div className="section-title">
          <div>
            <h2>Nearby activity</h2>
            <p>Students who have chosen to share a listing</p>
          </div>
          <button className="text-action" onClick={() => navigate('matches')}>
            View all <Icon name="arrow" size={15} />
          </button>
        </div>
        {loading ? (
          <div className="loading-inline">
            <span className="spinner" />Loading listings…
          </div>
        ) : loadError ? (
          <p className="inline-error" role="alert">
            {loadError}{' '}
            <button className="text-action" onClick={() => setRetry((value) => value + 1)}>
              Try again
            </button>
          </p>
        ) : listings.length ? (
          <div className="listing-stack">
            {listings.map((listing) => (
              <div key={listing.id} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <ListingCard
                  listing={listing}
                  onClick={() => {
                    setSelectedListing(listing)
                    navigate('student')
                  }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', paddingRight: 6 }}>
                  <button
                    className="button button-soft"
                    style={{ minHeight: 32, fontSize: 11, padding: '0 12px' }}
                    onClick={() => setRequestListing(listing)}
                  >
                    Send Request
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No nearby listings yet"
            body="When students post a cash request or offer, it will show here. Your home feed does not use sample profiles."
            action={
              <button className="button button-soft" onClick={() => navigate('matches')}>
                Explore listings
              </button>
            }
          />
        )}
      </section>

      {/* Recent Transactions (last 3) */}
      <section className="section-block recent-block">
        <div className="section-title">
          <div>
            <h2>Your exchanges</h2>
            <p>Meetups and payment status, together</p>
          </div>
          <button className="text-action" onClick={() => navigate('transactions')}>
            See all <Icon name="arrow" size={15} />
          </button>
        </div>
        {loading ? (
          <div className="loading-inline">
            <span className="spinner" />Loading exchanges…
          </div>
        ) : loadError ? (
          <p className="quiet-empty">Exchange activity could not be refreshed.</p>
        ) : exchanges.length ? (
          <div className="exchange-mini-list">
            {exchanges.map((exchange) => (
              <button
                key={exchange.id}
                className="exchange-mini"
                onClick={() => {
                  setSelectedExchange(exchange)
                  navigate('meetup')
                }}
              >
                <Avatar name={exchange.other_user?.full_name || 'Student'} size="sm" />
                <span>
                  <strong>{exchange.other_user?.full_name || 'Student'}</strong>
                  <small>{exchange.status.replaceAll('_', ' ')}</small>
                </span>
                <b>{money(exchange.amount)}</b>
              </button>
            ))}
          </div>
        ) : (
          <p className="quiet-empty">No exchanges started yet. Your matches will appear here.</p>
        )}
      </section>

      {mine.length > 0 && (
        <section className="own-listings">
          <div className="section-title">
            <div>
              <h2>Your listings</h2>
              <p>You can pause or cancel an active listing.</p>
            </div>
          </div>
          {mine.slice(0, 2).map((listing) => (
            <div className="own-listing" key={listing.id}>
              <span className={`listing-kind ${listing.kind}`}>
                {listing.kind === 'need' ? 'Need cash' : 'Have cash'}
              </span>
              <strong>
                {money(listing.amount_min)}
                {listing.amount_max !== listing.amount_min ? `–${money(listing.amount_max)}` : ''}
              </strong>
              <span className="status-pill neutral">{listing.status}</span>
            </div>
          ))}
        </section>
      )}

      <section className="safety-tip">
        <span>
          <Icon name="shield" />
        </span>
        <div>
          <strong>Keep exchanges safe</strong>
          <p>Meet in a public campus spot. ONPay never asks for your UPI PIN.</p>
        </div>
        <button onClick={() => navigate('help')} aria-label="Safety tips">
          <Icon name="arrow" size={16} />
        </button>
      </section>

      {requestListing && (
        <SendMatchRequestModal
          listing={requestListing}
          onClose={() => setRequestListing(null)}
          onSuccess={() => {
            setRequestListing(null)
            setRetry((r) => r + 1)
          }}
        />
      )}
    </div>
  )
}

export default HomePage

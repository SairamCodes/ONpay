import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Coordinates, Exchange, GeoStatus, Listing, Screen } from '../types'
import { api } from '../api'
import { PageTitle } from '../components/PageTitle'
import { Icon } from '../components/Icon'
import { ListingCard } from '../components/ListingCard'
import { EmptyState } from '../components/EmptyState'
import { SendMatchRequestModal } from '../features/match-requests/SendMatchRequestModal'

export function MatchesPage({
  coordinates,
  geoStatus,
  navigate,
  setSelectedListing,
  setSelectedExchange,
  setError,
}: {
  coordinates: Coordinates | null
  geoStatus: GeoStatus
  navigate: (screen: Screen) => void
  setSelectedListing: (listing: Listing) => void
  setSelectedExchange: (exchange: Exchange) => void
  setError: (message: string) => void
}) {
  const [filter, setFilter] = useState('all')
  const [draft, setDraft] = useState({ minimum: '', maximum: '', location: '', availability: '' })
  const [filters, setFilters] = useState(draft)
  const [listings, setListings] = useState<Listing[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [retry, setRetry] = useState(0)
  const [sort, setSort] = useState('recent')
  const [requestListing, setRequestListing] = useState<Listing | null>(null)
  const [successToast, setSuccessToast] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    const query = new URLSearchParams({ kind: filter })
    if (coordinates) {
      query.set('latitude', String(coordinates.latitude))
      query.set('longitude', String(coordinates.longitude))
      query.set('radius_km', '25')
    }
    if (filters.minimum) query.set('min_amount', String(Math.round(Number(filters.minimum) * 100)))
    if (filters.maximum) query.set('max_amount', String(Math.round(Number(filters.maximum) * 100)))
    if (filters.location.trim()) query.set('location', filters.location.trim())
    if (filters.availability.trim()) query.set('availability', filters.availability.trim())

    try {
      const data = await api(`/api/listings?${query.toString()}`)
      setListings(data.listings)
      setLoadError('')
    } catch (failure) {
      setLoadError(failure instanceof Error ? failure.message : 'Could not load matches')
    } finally {
      setLoading(false)
    }
  }, [filter, filters, coordinates, retry])

  useEffect(() => {
    load()
  }, [load])

  const ordered = useMemo(
    () => [...listings].sort((a, b) => (sort === 'amount' ? a.amount_min - b.amount_min : 0)),
    [listings, sort]
  )

  return (
    <div className="page-stack">
      <PageTitle
        title="Nearby matches"
        subtitle={
          coordinates
            ? 'Active listings within 25 km of your approximate current area.'
            : geoStatus === 'denied'
            ? 'Location is blocked; browse all listings or choose a campus area.'
            : 'Enable location to filter by distance, or browse all active listings.'
        }
      />

      {successToast && (
        <div
          style={{
            background: '#d1f5e0',
            color: 'var(--green)',
            padding: '10px 14px',
            borderRadius: 12,
            fontSize: 12,
            fontWeight: 600,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>✓ {successToast}</span>
          <button
            onClick={() => setSuccessToast('')}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 16 }}
          >
            ×
          </button>
        </div>
      )}

      <div className="filter-row">
        {[
          ['all', 'All'],
          ['need', 'Need cash'],
          ['have', 'Have cash'],
        ].map(([value, label]) => (
          <button
            key={value}
            className={`filter-chip ${filter === value ? 'selected' : ''}`}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <form
        className="match-filter-panel"
        onSubmit={(event) => {
          event.preventDefault()
          setFilters({ ...draft })
        }}
      >
        <label>
          Minimum ₹
          <input
            type="number"
            min="1"
            step="1"
            value={draft.minimum}
            onChange={(event) => setDraft({ ...draft, minimum: event.target.value })}
            placeholder="Any"
          />
        </label>
        <label>
          Maximum ₹
          <input
            type="number"
            min="1"
            step="1"
            value={draft.maximum}
            onChange={(event) => setDraft({ ...draft, maximum: event.target.value })}
            placeholder="Any"
          />
        </label>
        <label>
          Campus or area
          <input
            maxLength={120}
            value={draft.location}
            onChange={(event) => setDraft({ ...draft, location: event.target.value })}
            placeholder="Any meeting area"
          />
        </label>
        <label>
          Preferred time
          <input
            maxLength={80}
            value={draft.availability}
            onChange={(event) => setDraft({ ...draft, availability: event.target.value })}
            placeholder="Any time"
          />
        </label>
        <button className="button button-soft">Apply filters</button>
        <button
          type="button"
          className="text-action"
          onClick={() => {
            const clear = { minimum: '', maximum: '', location: '', availability: '' }
            setDraft(clear)
            setFilters(clear)
          }}
        >
          Clear
        </button>
      </form>

      <div className="sort-row">
        <span>
          {listings.length} {listings.length === 1 ? 'listing' : 'listings'}
        </span>
        <label>
          Sort{' '}
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="recent">Recently posted</option>
            <option value="amount">Amount</option>
          </select>
        </label>
      </div>

      {loading ? (
        <div className="loading-inline">
          <span className="spinner" />Finding matches…
        </div>
      ) : loadError ? (
        <p className="inline-error" role="alert">
          {loadError}{' '}
          <button className="text-action" onClick={() => setRetry((value) => value + 1)}>
            Try again
          </button>
        </p>
      ) : ordered.length ? (
        <div className="match-list">
          {ordered.map((listing) => (
            <article key={listing.id} className="match-card">
              <ListingCard
                listing={listing}
                onClick={() => {
                  setSelectedListing(listing)
                  navigate('student')
                }}
              />
              <div className="match-detail">
                <span>
                  <Icon name="clock" size={15} /> {listing.availability}
                </span>
                <span>
                  <Icon name="pin" size={15} /> {listing.location}
                </span>
              </div>
              <div className="match-buttons">
                <button
                  className="button button-soft"
                  onClick={() => {
                    setSelectedListing(listing)
                    navigate('student')
                  }}
                >
                  View details
                </button>
                <button
                  className="button button-primary"
                  onClick={() => setRequestListing(listing)}
                >
                  Send Request
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No matching listings"
          body="Try another filter or publish a request or offer so students can find you."
          action={
            <div className="empty-actions">
              <button className="button button-primary" onClick={() => navigate('need')}>
                I need cash
              </button>
              <button className="button button-soft" onClick={() => navigate('have')}>
                I have cash
              </button>
            </div>
          }
        />
      )}

      {requestListing && (
        <SendMatchRequestModal
          listing={requestListing}
          onClose={() => setRequestListing(null)}
          onSuccess={() => {
            setRequestListing(null)
            setSuccessToast('Match request sent successfully!')
          }}
        />
      )}
    </div>
  )
}

export default MatchesPage

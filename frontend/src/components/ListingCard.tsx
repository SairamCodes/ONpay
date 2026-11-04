import type { Listing } from '../types'
import { money } from '../utils'
import { Avatar } from './Avatar'
import { Icon } from './Icon'

export function ListingCard({ listing, onClick }: { listing: Listing; onClick: () => void }) {
  const ownerName = listing.owner?.full_name || listing.owner_name || 'Student'
  const isVerified = listing.owner?.verified || listing.verified
  const college = listing.owner?.college || 'Student'

  return (
    <button className="listing-card" onClick={onClick}>
      <Avatar name={ownerName} size="md" />
      <span className="listing-info">
        <span className="listing-name">
          {ownerName}{' '}
          {isVerified && (
            <span className="verified-dot" title="Contact verified">
              <Icon name="check" size={11} />
            </span>
          )}
        </span>
        <small>
          {college} · {listing.location}
          {listing.distance_km != null ? ` · ${listing.distance_km} km away` : ''}
        </small>
        <span className={`listing-kind ${listing.kind}`}>
          {listing.kind === 'need' ? 'Needs cash' : 'Has cash'}
        </span>
      </span>
      <span className="listing-amount">
        <strong>
          {money(listing.amount_min)}
          {listing.amount_max !== listing.amount_min ? `–${money(listing.amount_max)}` : ''}
        </strong>
        <small>{listing.availability}</small>
      </span>
    </button>
  )
}

export default ListingCard

import type { Listing, Screen } from '../types'
import { money } from '../utils'
import { api, json } from '../api'
import { Avatar } from '../components/Avatar'
import { Icon } from '../components/Icon'

export function StudentPage({
  listing,
  navigate,
  setChatTarget,
  setError,
}: {
  listing: Listing
  navigate: (screen: Screen) => void
  setChatTarget: (id: string | null) => void
  setError: (message: string) => void
}) {
  const ownerId = listing.owner?.id || listing.owner_id || ''
  const ownerName = listing.owner?.full_name || listing.owner_name || 'Student'
  const college = listing.owner?.college || 'Student'
  const isVerified = listing.owner?.verified || listing.verified

  const reportOrBlock = async (action: 'report' | 'block') => {
    try {
      if (action === 'block') {
        await api('/api/blocks', json({ user_id: ownerId }))
        setError('Student blocked. Their listings and messages are hidden from you.')
      } else {
        await api('/api/reports', json({ user_id: ownerId, category: 'profile_report', details: '' }))
        setError('Thanks. Your report has been sent for review.')
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not submit this request')
    }
  }

  return (
    <div className="page-stack">
      <button className="back-link" onClick={() => navigate('matches')}>
        <Icon name="back" size={17} /> Back to matches
      </button>
      <section className="student-profile panel">
        <Avatar name={ownerName} size="lg" />
        <h1>{ownerName}</h1>
        <p>{college}</p>
        {isVerified && (
          <span className="verified-label">
            <Icon name="shield" size={15} /> Contact verified
          </span>
        )}
        <div className={`student-offer ${listing.kind}`}>
          <span>{listing.kind === 'need' ? 'Needs cash' : 'Has cash'}</span>
          <strong>
            {money(listing.amount_min)}
            {listing.amount_max !== listing.amount_min ? ` – ${money(listing.amount_max)}` : ''}
          </strong>
        </div>
        <div className="detail-row">
          <span>Meeting area</span>
          <strong>{listing.location}</strong>
        </div>
        <div className="detail-row">
          <span>Availability</span>
          <strong>{listing.availability}</strong>
        </div>
        {listing.note && <div className="note-card">“{listing.note}”</div>}
        <p className="privacy-note">
          <Icon name="info" size={15} /> Ratings and exchange counts will appear only after real, verified exchanges.
        </p>
        <button
          className="button button-primary button-wide"
          onClick={() => {
            setChatTarget(ownerId)
            navigate('chats')
          }}
        >
          Message student <Icon name="chat" />
        </button>
        <div className="moderation-links">
          <button onClick={() => reportOrBlock('report')}>Report</button>
          <button onClick={() => reportOrBlock('block')}>Block</button>
        </div>
      </section>
    </div>
  )
}

export default StudentPage

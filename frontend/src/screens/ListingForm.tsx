import { useState, type FormEvent } from 'react'
import type { Coordinates, Screen } from '../types'
import { api, json } from '../api'
import { PageTitle } from '../components/PageTitle'
import { Icon } from '../components/Icon'

export function ListingForm({
  kind,
  locationLabel,
  coordinates,
  navigate,
  setError,
}: {
  kind: 'need' | 'have'
  locationLabel: string
  coordinates: Coordinates | null
  navigate: (screen: Screen) => void
  setError: (message: string) => void
}) {
  const [minimum, setMinimum] = useState('')
  const [maximum, setMaximum] = useState('')
  const [location, setLocation] = useState(locationLabel)
  const [availability, setAvailability] = useState('Today, 2:00 PM – 4:00 PM')
  const [note, setNote] = useState('')
  const [searchRadiusKm, setSearchRadiusKm] = useState(25)
  const [saving, setSaving] = useState(false)

  const isNeed = kind === 'need'

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const min = Math.round(Number(minimum) * 100)
      const max = isNeed ? min : Math.round(Number(maximum || minimum) * 100)
      await api(
        '/api/listings',
        json({
          kind,
          amount_min: min,
          amount_max: max,
          location,
          availability,
          note,
          search_radius_km: searchRadiusKm,
          ...(coordinates || {}),
        })
      )
      navigate('home')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not publish this listing')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page-stack form-page">
      <PageTitle
        title={isNeed ? 'Request cash' : 'Offer cash'}
        subtitle={
          isNeed
            ? 'Find a student who can exchange cash for your UPI payment.'
            : 'Share how much cash you can exchange for a UPI payment.'
        }
        action={
          <button className="icon-button" onClick={() => navigate('home')} aria-label="Close">
            <Icon name="close" />
          </button>
        }
      />
      <div className={`form-hero ${isNeed ? 'blue-hero' : 'green-hero'}`}>
        <span className="form-hero-icon">
          <Icon name={isNeed ? 'arrow' : 'check'} size={24} />
        </span>
        <div>
          <b>{isNeed ? 'I Need Cash' : 'I Have Cash'}</b>
          <small>
            {isNeed
              ? 'You pay in your UPI app after meeting.'
              : 'You receive the UPI payment after handing over cash.'}
          </small>
        </div>
      </div>
      <form className="panel stack-form" onSubmit={submit}>
        <label>
          {isNeed ? 'Cash amount' : 'Available cash'}
          <div className="money-input">
            <span>₹</span>
            <input
              type="number"
              required
              min="1"
              max="2500"
              step="1"
              value={minimum}
              onChange={(e) => setMinimum(e.target.value)}
              placeholder="500"
            />
          </div>
          <small className="field-hint">Choose an amount from ₹1 to ₹2,500 for this exchange.</small>
        </label>
        {!isNeed && (
          <label>
            Minimum amount for partial exchanges <span className="optional">(optional)</span>
            <div className="money-input">
              <span>₹</span>
              <input
                type="number"
                min="1"
                max="2500"
                step="1"
                value={maximum}
                onChange={(e) => setMaximum(e.target.value)}
                placeholder="Same as available cash"
              />
            </div>
          </label>
        )}
        <label>
          Meeting location
          <input
            required
            minLength={2}
            maxLength={180}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Library entrance, Aditya University"
          />
          <small className="field-hint">
            Use a public place. If location is enabled, ONPay uses a rounded approximate position for nearby matching; exact coordinates are never shown.
          </small>
        </label>
        <label>
          Search radius
          <div className="radius-selector">
            {[1, 2, 5, 10, 25, 50].map((r) => (
              <button
                key={r}
                type="button"
                className={searchRadiusKm === r ? 'active' : ''}
                onClick={() => setSearchRadiusKm(r)}
              >
                {r}km
              </button>
            ))}
          </div>
        </label>
        <label>
          Preferred time
          <input
            required
            maxLength={120}
            value={availability}
            onChange={(e) => setAvailability(e.target.value)}
            placeholder="Today after 3 PM"
          />
        </label>
        <label>
          Note <span className="optional">(optional)</span>
          <textarea
            maxLength={500}
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={isNeed ? 'e.g. Need cash for lunch' : 'e.g. Can meet near the main gate'}
          />
        </label>
        <button
          className={`button button-primary button-wide ${isNeed ? '' : 'button-green'}`}
          disabled={saving}
        >
          {saving ? 'Publishing…' : isNeed ? 'Find a match' : 'Publish offer'}{' '}
          <Icon name="arrow" />
        </button>
      </form>
      <div className="safe-note">
        <Icon name="info" size={17} /> Creating a listing does not initiate a payment or confirm an exchange.
      </div>
    </div>
  )
}

export default ListingForm

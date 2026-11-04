import type { Exchange, Screen } from '../types'
import { PageTitle } from '../components/PageTitle'
import { Icon } from '../components/Icon'
import { MatchRequestsPanel } from '../features/match-requests/MatchRequestsPanel'

interface MatchRequestsScreenProps {
  navigate: (screen: Screen) => void
  setSelectedExchange: (exchange: Exchange) => void
}

export function MatchRequestsScreen({ navigate, setSelectedExchange }: MatchRequestsScreenProps) {
  return (
    <div className="page-stack">
      <button className="back-link" onClick={() => navigate('home')}>
        <Icon name="back" size={17} /> Home
      </button>
      <PageTitle
        title="Match Requests"
        subtitle="Manage your incoming and outgoing peer exchange requests."
      />
      <MatchRequestsPanel
        navigate={navigate}
        onSelectExchange={(exchange) => {
          setSelectedExchange(exchange)
          navigate('meetup')
        }}
      />
    </div>
  )
}

export default MatchRequestsScreen

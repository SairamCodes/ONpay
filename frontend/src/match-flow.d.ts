export function matchAndNavigate<T extends { id: string; status: string }>(
  api: (path: string, options: RequestInit) => Promise<{ exchange?: T }>,
  listingId: string,
  amount: number,
  setSelectedExchange: (exchange: T) => void,
  navigate: (screen: 'meetup') => void,
  refreshListings: () => void,
): Promise<T>

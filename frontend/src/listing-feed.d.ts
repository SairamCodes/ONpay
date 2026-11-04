type ListingFeedCoordinates = { latitude: number; longitude: number }
type AvailableListing = { id: string; status: string; [key: string]: unknown }

export function fetchAvailableListings<T extends AvailableListing>(
  api: (path: string) => Promise<{ listings?: T[] }>,
  coordinates: ListingFeedCoordinates | null,
): Promise<T[]>

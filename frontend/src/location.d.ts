export type LocationDetails = {
  latitude: number
  longitude: number
  accuracy: number
  timestamp: number
}

export type ResolvedLocation = LocationDetails & {
  placeName: string
  message: string
}

export function requestCurrentLocation(options?: {
  geolocation?: Geolocation
  isSecureContext?: boolean
  hostname?: string
}): Promise<LocationDetails>

export function detectCurrentLocation(options: {
  geolocation?: Geolocation
  reverseGeocode: (details: LocationDetails) => Promise<{
    status?: string
    label?: string | null
    attribution?: string | null
    reason?: string
  }>
  isSecureContext?: boolean
  hostname?: string
}): Promise<ResolvedLocation>

export function saveManualLocation(label: string, save: (label: string) => Promise<unknown>): Promise<string>

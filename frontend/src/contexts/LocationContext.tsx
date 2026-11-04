import { createContext, useContext } from 'react';

interface LocationContextValue {
  locationLabel: string;
  geoCoordinates: { latitude: number; longitude: number } | null;
  geoLabel: string;
  geoStatus: string;
  geoMessage: string;
  refreshLocation: () => void;
}

export const LocationContext = createContext<LocationContextValue>({
  locationLabel: '',
  geoCoordinates: null,
  geoLabel: '',
  geoStatus: '',
  geoMessage: '',
  refreshLocation: () => {},
});
export const useLocation = () => useContext(LocationContext);

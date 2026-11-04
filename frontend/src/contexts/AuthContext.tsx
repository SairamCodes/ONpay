import { createContext, useContext } from 'react';
import type { User } from '../types';

interface AuthContextValue {
  user: User | null;
  setUser: (u: User | null) => void;
  ready: boolean;
}

export const AuthContext = createContext<AuthContextValue>({ user: null, setUser: () => {}, ready: false });
export const useAuth = () => useContext(AuthContext);

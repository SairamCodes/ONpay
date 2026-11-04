import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { ONPayWebSocket } from '../ws';

interface WSContextValue {
  ws: ONPayWebSocket | null;
  connected: boolean;
}

export const WebSocketContext = createContext<WSContextValue>({ ws: null, connected: false });
export const useWebSocket = () => useContext(WebSocketContext);

export function WebSocketProvider({ authenticated, children }: { authenticated: boolean; children: React.ReactNode }) {
  const wsRef = useRef<ONPayWebSocket | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!authenticated) {
      wsRef.current?.disconnect();
      wsRef.current = null;
      setConnected(false);
      return;
    }
    const ws = new ONPayWebSocket();
    ws.on('_status', (data: { connected: boolean }) => setConnected(data.connected));
    ws.connect();
    wsRef.current = ws;
    return () => { ws.disconnect(); };
  }, [authenticated]);

  return (
    <WebSocketContext.Provider value={{ ws: wsRef.current, connected }}>
      {children}
    </WebSocketContext.Provider>
  );
}

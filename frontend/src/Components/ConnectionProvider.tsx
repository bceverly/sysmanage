import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { connectionMonitor, ConnectionStatus } from '../Services/connectionMonitor';
import ServerDownModal from './ServerDownModal';

interface ConnectionContextType {
  status: ConnectionStatus;
  markConnectionFailed: (error?: string) => void;
  markConnectionRestored: () => void;
}

const ConnectionContext = createContext<ConnectionContextType>({
  status: {
    isConnected: true,
    lastConnected: null,
    retryCount: 0,
    nextRetryIn: 0,
  },
  markConnectionFailed: () => {},
  markConnectionRestored: () => {},
});

export const useConnection = () => {
  const context = useContext(ConnectionContext);
  if (!context) {
    throw new Error('useConnection must be used within a ConnectionProvider');
  }
  return context;
};

interface ConnectionProviderProps {
  children: React.ReactNode;
}

const ConnectionProvider: React.FC<ConnectionProviderProps> = ({ children }) => {
  const [status, setStatus] = useState<ConnectionStatus>({
    isConnected: true,
    lastConnected: new Date(),
    retryCount: 0,
    nextRetryIn: 0,
  });

  useEffect(() => {
    // Subscribe to connection status changes
    const unsubscribe = connectionMonitor.onStatusChange(setStatus);

    // Set up global error handlers for fetch requests
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (...args) => {
      try {
        const response = await originalFetch(...args);
        
        // If request succeeds, mark connection as restored
        if (response.ok) {
          connectionMonitor.markConnectionRestored();
        }
        
        // If request fails with network/server error, mark connection as failed
        if (!response.ok && response.status >= 500) {
          connectionMonitor.markConnectionFailed(`Server error: ${response.status}`);
        }
        
        return response;
      } catch (error) {
        // Network errors (server down, no internet, etc.)
        if (error instanceof TypeError && error.message.includes('fetch')) {
          connectionMonitor.markConnectionFailed('Network error: Unable to reach server');
        }
        throw error;
      }
    };

    // Cleanup
    return () => {
      unsubscribe();
      globalThis.fetch = originalFetch;
      connectionMonitor.destroy();
    };
  }, []);

  const contextValue: ConnectionContextType = useMemo(() => ({
    status,
    markConnectionFailed: connectionMonitor.markConnectionFailed.bind(connectionMonitor),
    markConnectionRestored: connectionMonitor.markConnectionRestored.bind(connectionMonitor),
  }), [status]);

  return (
    <ConnectionContext.Provider value={contextValue}>
      {children}
      <ServerDownModal open={!status.isConnected} />
    </ConnectionContext.Provider>
  );
};

export default ConnectionProvider;
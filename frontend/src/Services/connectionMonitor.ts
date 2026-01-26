/**
 * Connection monitoring service for detecting server connectivity issues
 * and managing fallback behavior with exponential backoff retry logic.
 */

import axiosInstance from './api';

interface ConnectionStatus {
  isConnected: boolean;
  lastConnected: Date | null;
  retryCount: number;
  nextRetryIn: number;
  error?: string;
}

interface ConnectionMonitorOptions {
  initialRetryDelay: number; // Initial delay in seconds
  maxRetryDelay: number; // Maximum delay in seconds
  maxRetries: number; // Maximum number of retries before giving up
  backoffMultiplier: number; // Exponential backoff multiplier
  healthCheckInterval: number; // Interval for health checks in seconds
}

type ConnectionStatusCallback = (status: ConnectionStatus) => void;

class ConnectionMonitor {
  private status: ConnectionStatus = {
    isConnected: true,
    lastConnected: new Date(),
    retryCount: 0,
    nextRetryIn: 0,
  };

  private readonly options: ConnectionMonitorOptions = {
    initialRetryDelay: 5, // Start with 5 seconds
    maxRetryDelay: 300, // Max 5 minutes
    maxRetries: 10, // Try 10 times before giving up
    backoffMultiplier: 2, // Double the delay each time
    healthCheckInterval: 60, // Check every 60 seconds when connected
  };

  private readonly callbacks: Set<ConnectionStatusCallback> = new Set();
  private retryTimeoutId: number | null = null;
  private healthCheckTimeoutId: number | null = null;
  private isRetrying = false;

  constructor(options?: Partial<ConnectionMonitorOptions>) {
    this.options = { ...this.options, ...options };
    // Only start health checks if user is authenticated
    if (localStorage.getItem('bearer_token')) {
      this.startHealthCheck();
    }
  }

  /**
   * Subscribe to connection status changes
   */
  onStatusChange(callback: ConnectionStatusCallback): () => void {
    this.callbacks.add(callback);
    // Immediately call with current status
    callback(this.status);
    
    // Return unsubscribe function
    return () => {
      this.callbacks.delete(callback);
    };
  }

  /**
   * Get current connection status
   */
  getStatus(): ConnectionStatus {
    return { ...this.status };
  }

  /**
   * Mark connection as failed and start retry process
   */
  markConnectionFailed(error?: string): void {
    if (this.status.isConnected) {
      console.warn('Connection lost:', error);
      this.status = {
        ...this.status,
        isConnected: false,
        error: error || 'Connection to server lost',
      };
      this.notifyStatusChange();
      this.stopHealthCheck();
      this.startRetryProcess();
    }
  }

  /**
   * Mark connection as restored
   */
  markConnectionRestored(): void {
    if (!this.status.isConnected) {
      console.log('Connection restored');
      this.status = {
        isConnected: true,
        lastConnected: new Date(),
        retryCount: 0,
        nextRetryIn: 0,
        error: undefined,
      };
      this.notifyStatusChange();
      this.stopRetryProcess();
      this.startHealthCheck();
    }
  }

  /**
   * Manually trigger a retry attempt
   */
  retryNow(): void {
    if (!this.status.isConnected && !this.isRetrying) {
      this.performRetry();
    }
  }

  /**
   * Reset retry counter (useful after user intervention)
   */
  resetRetryCount(): void {
    this.status.retryCount = 0;
    this.notifyStatusChange();
  }

  /**
   * Cleanup resources
   */
  destroy(): void {
    this.stopRetryProcess();
    this.stopHealthCheck();
    this.callbacks.clear();
  }

  private startHealthCheck(): void {
    this.stopHealthCheck();
    this.healthCheckTimeoutId = globalThis.setTimeout(() => {
      this.performHealthCheck();
    }, this.options.healthCheckInterval * 1000);
  }

  private stopHealthCheck(): void {
    if (this.healthCheckTimeoutId) {
      clearTimeout(this.healthCheckTimeoutId);
      this.healthCheckTimeoutId = null;
    }
  }

  private async performHealthCheck(): Promise<void> {
    // Don't perform health checks if user is not authenticated
    if (!localStorage.getItem('bearer_token')) {
      // Schedule next check but don't actually perform it
      this.startHealthCheck();
      return;
    }
    
    try {
      // Simple health check - try to fetch from the API
      const response = await axiosInstance.head('/api/health', {
        timeout: 15000,
      });

      if (response.status === 200) {
        this.markConnectionRestored();
      } else {
        throw new Error(`Health check failed: ${response.status}`);
      }
    } catch (error) {
      this.markConnectionFailed(error instanceof Error ? error.message : 'Health check failed');
    }

    // Schedule next health check if still connected
    if (this.status.isConnected) {
      this.startHealthCheck();
    }
  }

  private startRetryProcess(): void {
    if (this.status.retryCount >= this.options.maxRetries) {
      console.error('Maximum retry attempts reached');
      this.status.error = 'Server is down. Please contact support.';
      this.notifyStatusChange();
      return;
    }

    const delay = this.calculateRetryDelay();
    this.status.nextRetryIn = delay;
    this.notifyStatusChange();

    this.startRetryCountdown(delay);
  }

  private startRetryCountdown(_delaySeconds: number): void {
    const updateCountdown = () => {
      if (this.status.nextRetryIn > 0) {
        this.status.nextRetryIn--;
        this.notifyStatusChange();
        this.retryTimeoutId = globalThis.setTimeout(updateCountdown, 1000);
      } else {
        this.performRetry();
      }
    };

    this.retryTimeoutId = globalThis.setTimeout(updateCountdown, 1000);
  }

  private stopRetryProcess(): void {
    if (this.retryTimeoutId) {
      clearTimeout(this.retryTimeoutId);
      this.retryTimeoutId = null;
    }
    this.isRetrying = false;
  }

  private async performRetry(): Promise<void> {
    if (this.isRetrying) return;
    
    // Don't retry if user is not authenticated
    if (!localStorage.getItem('bearer_token')) {
      this.stopRetryProcess();
      return;
    }
    
    this.isRetrying = true;
    this.status.retryCount++;
    this.notifyStatusChange();

    try {
      // Try to connect to the server
      const response = await axiosInstance.head('/api/health', {
        timeout: 15000,
      });

      if (response.status === 200) {
        this.markConnectionRestored();
      } else {
        throw new Error(`Retry failed: ${response.status}`);
      }
    } catch (error) {
      // nosemgrep: javascript.lang.security.audit.unsafe-formatstring
      console.warn(`Retry attempt ${this.status.retryCount} failed:`, error);
      this.isRetrying = false;
      
      // Schedule next retry
      setTimeout(() => {
        if (!this.status.isConnected) {
          this.startRetryProcess();
        }
      }, 1000);
    }
  }

  private calculateRetryDelay(): number {
    const delay = Math.min(
      this.options.initialRetryDelay * Math.pow(this.options.backoffMultiplier, this.status.retryCount),
      this.options.maxRetryDelay
    );
    return Math.floor(delay);
  }

  private notifyStatusChange(): void {
    this.callbacks.forEach(callback => {
      try {
        callback({ ...this.status });
      } catch (error) {
        console.error('Error in connection status callback:', error);
      }
    });
  }
}

// Global connection monitor instance
export const connectionMonitor = new ConnectionMonitor();

// Export types
export type { ConnectionStatus, ConnectionMonitorOptions };
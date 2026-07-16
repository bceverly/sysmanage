// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for the connection monitor service.
 *
 * The module exports a singleton `connectionMonitor` constructed at import
 * time.  Because no bearer_token is set at import, the constructor does NOT
 * start a health-check timer, so importing is side-effect free for timers.
 * We drive the public API (subscribe / mark failed / mark restored / retry /
 * reset / destroy) with fake timers and a mocked axios `head`.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import axiosInstance from '../api';
import { connectionMonitor, type ConnectionStatus } from '../connectionMonitor';

vi.mock('../api', () => ({
  default: {
    head: vi.fn(),
  },
}));

const headOk = () => ({
  status: 200,
  statusText: 'OK',
  headers: {},
  config: {} as any,
  data: undefined,
});

describe('connectionMonitor service', () => {
  let logSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;
  let errSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    logSpy = vi.spyOn(window.console, 'log').mockImplementation(() => {});
    warnSpy = vi.spyOn(window.console, 'warn').mockImplementation(() => {});
    errSpy = vi.spyOn(window.console, 'error').mockImplementation(() => {});
    localStorage.clear();
    // Ensure the shared singleton is back to a clean connected state and no
    // timers are pending from a previous test.
    connectionMonitor.destroy();
    connectionMonitor.markConnectionRestored(); // no-op if already connected
  });

  afterEach(() => {
    connectionMonitor.destroy();
    vi.clearAllTimers();
    vi.useRealTimers();
    logSpy.mockRestore();
    warnSpy.mockRestore();
    errSpy.mockRestore();
  });

  describe('getStatus / onStatusChange', () => {
    it('returns a copy of the current status', () => {
      const status = connectionMonitor.getStatus();
      expect(status.isConnected).toBe(true);
      expect(status.retryCount).toBe(0);
      // Mutating the returned copy must not affect internal state.
      status.retryCount = 99;
      expect(connectionMonitor.getStatus().retryCount).toBe(0);
    });

    it('invokes the callback immediately on subscribe and returns an unsubscribe fn', () => {
      const cb = vi.fn();
      const unsubscribe = connectionMonitor.onStatusChange(cb);

      expect(cb).toHaveBeenCalledTimes(1);
      expect(cb.mock.calls[0][0].isConnected).toBe(true);
      expect(typeof unsubscribe).toBe('function');

      // After unsubscribe, further notifications are not delivered.
      unsubscribe();
      cb.mockClear();
      connectionMonitor.markConnectionFailed('x');
      expect(cb).not.toHaveBeenCalled();
    });
  });

  describe('markConnectionFailed', () => {
    it('flips to disconnected, notifies, and uses provided error', () => {
      const updates: ConnectionStatus[] = [];
      connectionMonitor.onStatusChange((s) => updates.push(s));
      updates.length = 0; // drop the immediate initial call

      connectionMonitor.markConnectionFailed('down hard');

      const status = connectionMonitor.getStatus();
      expect(status.isConnected).toBe(false);
      expect(status.error).toBe('down hard');
      expect(updates.length).toBeGreaterThan(0);
      expect(updates.some((u) => u.isConnected === false)).toBe(true);
    });

    it('falls back to a default error message', () => {
      connectionMonitor.markConnectionFailed();
      expect(connectionMonitor.getStatus().error).toBe('Connection to server lost');
    });

    it('is a no-op when already disconnected', () => {
      connectionMonitor.markConnectionFailed('first');
      const cb = vi.fn();
      connectionMonitor.onStatusChange(cb);
      cb.mockClear();

      connectionMonitor.markConnectionFailed('second');

      // Still the first error, no new notification from the second call.
      expect(connectionMonitor.getStatus().error).toBe('first');
      expect(cb).not.toHaveBeenCalled();
    });
  });

  describe('markConnectionRestored', () => {
    it('resets status to connected and clears the error/retry count', () => {
      connectionMonitor.markConnectionFailed('lost');
      expect(connectionMonitor.getStatus().isConnected).toBe(false);

      connectionMonitor.markConnectionRestored();

      const status = connectionMonitor.getStatus();
      expect(status.isConnected).toBe(true);
      expect(status.retryCount).toBe(0);
      expect(status.nextRetryIn).toBe(0);
      expect(status.error).toBeUndefined();
    });

    it('is a no-op when already connected', () => {
      const cb = vi.fn();
      connectionMonitor.onStatusChange(cb);
      cb.mockClear();

      connectionMonitor.markConnectionRestored();
      expect(cb).not.toHaveBeenCalled();
    });
  });

  describe('resetRetryCount', () => {
    it('sets retryCount to 0 and notifies', () => {
      connectionMonitor.markConnectionFailed('lost');
      const cb = vi.fn();
      connectionMonitor.onStatusChange(cb);
      cb.mockClear();

      connectionMonitor.resetRetryCount();

      expect(connectionMonitor.getStatus().retryCount).toBe(0);
      expect(cb).toHaveBeenCalledTimes(1);
    });
  });

  describe('retryNow', () => {
    it('does nothing while connected', () => {
      connectionMonitor.retryNow();
      expect(axiosInstance.head).not.toHaveBeenCalled();
    });

    it('bails out of the retry when not authenticated', async () => {
      connectionMonitor.markConnectionFailed('lost');
      // no bearer_token in localStorage
      connectionMonitor.retryNow();
      await vi.runOnlyPendingTimersAsync();

      expect(axiosInstance.head).not.toHaveBeenCalled();
    });

    it('performs a health head request and restores on 200', async () => {
      localStorage.setItem('bearer_token', 'tok');
      vi.mocked(axiosInstance.head).mockResolvedValue(headOk());

      connectionMonitor.markConnectionFailed('lost');
      connectionMonitor.retryNow();
      // Let the head promise settle (performRetry -> markConnectionRestored).
      await Promise.resolve();
      await Promise.resolve();

      expect(axiosInstance.head).toHaveBeenCalledWith('/api/health', {
        timeout: 15000,
      });
      expect(connectionMonitor.getStatus().isConnected).toBe(true);
      expect(connectionMonitor.getStatus().retryCount).toBe(0);
    });

    it('increments retryCount and schedules another attempt on failure', async () => {
      localStorage.setItem('bearer_token', 'tok');
      vi.mocked(axiosInstance.head).mockRejectedValue(new Error('refused'));

      connectionMonitor.markConnectionFailed('lost');
      connectionMonitor.retryNow();
      // Let the rejected head promise settle.
      await Promise.resolve();
      await Promise.resolve();

      expect(axiosInstance.head).toHaveBeenCalledTimes(1);
      expect(connectionMonitor.getStatus().retryCount).toBe(1);
      expect(connectionMonitor.getStatus().isConnected).toBe(false);
    });
  });

  describe('retry countdown process', () => {
    it('counts down nextRetryIn each second then retries and restores', async () => {
      localStorage.setItem('bearer_token', 'tok');
      vi.mocked(axiosInstance.head).mockResolvedValue(headOk());

      // markConnectionFailed kicks off the retry process (startRetryProcess).
      connectionMonitor.markConnectionFailed('lost');

      // initialRetryDelay is 5s at retryCount 0 -> nextRetryIn should be 5.
      expect(connectionMonitor.getStatus().nextRetryIn).toBe(5);

      // Drive the full countdown (5 x 1s ticks) plus the performRetry that
      // fires once nextRetryIn hits 0.
      await vi.advanceTimersByTimeAsync(7 * 1000);

      expect(axiosInstance.head).toHaveBeenCalled();
      expect(connectionMonitor.getStatus().isConnected).toBe(true);
    });
  });

  describe('health check timer', () => {
    it('schedules and performs a health check that restores connection', async () => {
      localStorage.setItem('bearer_token', 'tok');
      vi.mocked(axiosInstance.head).mockResolvedValue(headOk());

      // Put the monitor into a failed state, then restore to (re)start the
      // health-check timer deterministically.
      connectionMonitor.markConnectionFailed('lost');
      connectionMonitor.markConnectionRestored();

      // healthCheckInterval default is 60s.
      await vi.advanceTimersByTimeAsync(60 * 1000);
      await vi.runOnlyPendingTimersAsync();

      expect(axiosInstance.head).toHaveBeenCalledWith('/api/health', {
        timeout: 15000,
      });
      expect(connectionMonitor.getStatus().isConnected).toBe(true);
    });

    it('skips the actual health check when unauthenticated but reschedules', async () => {
      // Start the health-check timer while authenticated...
      localStorage.setItem('bearer_token', 'tok');
      connectionMonitor.markConnectionFailed('lost');
      connectionMonitor.markConnectionRestored();

      // ...then drop auth before the timer fires.
      localStorage.removeItem('bearer_token');

      await vi.advanceTimersByTimeAsync(60 * 1000);

      // No head request because performHealthCheck bails when unauthenticated.
      expect(axiosInstance.head).not.toHaveBeenCalled();
    });

    it('marks connection failed when the health check throws', async () => {
      localStorage.setItem('bearer_token', 'tok');
      vi.mocked(axiosInstance.head).mockRejectedValue(new Error('timeout'));

      connectionMonitor.markConnectionFailed('lost');
      connectionMonitor.markConnectionRestored();

      await vi.advanceTimersByTimeAsync(60 * 1000);
      await vi.runOnlyPendingTimersAsync();

      expect(axiosInstance.head).toHaveBeenCalled();
      expect(connectionMonitor.getStatus().isConnected).toBe(false);
    });
  });

  describe('notifyStatusChange error handling', () => {
    it('swallows errors thrown by a callback and keeps notifying others', () => {
      const errSpy = vi.spyOn(window.console, 'error').mockImplementation(() => {});
      const good = vi.fn();
      // Throw only on the *notify* call, not on the immediate subscribe call
      // (onStatusChange's initial callback invocation is not wrapped in try).
      let calls = 0;
      connectionMonitor.onStatusChange(() => {
        calls += 1;
        if (calls > 1) {
          throw new Error('bad subscriber');
        }
      });
      connectionMonitor.onStatusChange(good);
      good.mockClear();

      // Trigger a notification (invokes both subscribers via notifyStatusChange).
      connectionMonitor.markConnectionFailed('lost');

      expect(good).toHaveBeenCalled();
      expect(errSpy).toHaveBeenCalled();
      errSpy.mockRestore();
    });
  });

  describe('destroy', () => {
    it('clears callbacks and pending timers', () => {
      const cb = vi.fn();
      connectionMonitor.onStatusChange(cb);
      connectionMonitor.markConnectionFailed('lost');
      cb.mockClear();

      connectionMonitor.destroy();

      // After destroy, subscribers are cleared; restoring should not call cb.
      connectionMonitor.markConnectionRestored();
      expect(cb).not.toHaveBeenCalled();
    });
  });
});

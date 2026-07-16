// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { useCallback, useRef } from 'react';

type RefreshCallback = () => Promise<void> | void;

let globalRefreshCallback: RefreshCallback | null = null;

export const useNotificationRefresh = () => {
  const refreshCallbackRef = useRef<RefreshCallback | null>(null);

  const registerRefresh = useCallback((callback: RefreshCallback) => {
    refreshCallbackRef.current = callback;
    globalRefreshCallback = callback;
  }, []);

  const unregisterRefresh = useCallback(() => {
    refreshCallbackRef.current = null;
    globalRefreshCallback = null;
  }, []);

  const triggerRefresh = useCallback(async () => {
    if (globalRefreshCallback) {
      await globalRefreshCallback();
    }
  }, []);

  return {
    registerRefresh,
    unregisterRefresh,
    triggerRefresh,
  };
};
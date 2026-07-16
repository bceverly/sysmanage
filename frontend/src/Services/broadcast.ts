// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from './api.js';

export interface BroadcastRequest {
  broadcast_action: string;
  message?: string | null;
  parameters?: Record<string, unknown>;
  tag_id?: string | null;
  platform?: string | null;
}

export interface BroadcastResponse {
  broadcast_id: string;
  broadcast_action: string;
  delivered_count: number;
  elapsed_ms: number;
  target_filter: string;
}

export const broadcastService = {
  async send(payload: BroadcastRequest): Promise<BroadcastResponse> {
    const r = await axiosInstance.post('/api/v1/broadcast', payload);
    return r.data;
  },
};

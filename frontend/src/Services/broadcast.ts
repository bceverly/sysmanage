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
    const r = await axiosInstance.post('/api/broadcast', payload);
    return r.data;
  },
};

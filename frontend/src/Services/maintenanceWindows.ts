import axiosInstance from './api.js';

export type WindowKind = 'allow' | 'blackout';
export type WindowRecurrence = 'once' | 'daily' | 'weekly';
export type ScopeType = 'all' | 'host' | 'tag';

export interface MaintenanceScope {
    id?: string;
    scope_type: ScopeType;
    host_id?: string | null;
    tag_id?: string | null;
}

export interface MaintenanceWindow {
    id: string;
    name: string;
    description: string | null;
    enabled: boolean;
    kind: WindowKind;
    recurrence: WindowRecurrence;
    timezone: string;
    start_time: string | null;
    duration_minutes: number | null;
    days_of_week: string[];
    starts_at: string | null;
    ends_at: string | null;
    scopes: MaintenanceScope[];
    created_at?: string | null;
    updated_at?: string | null;
}

// Create/update payload — the server assigns id/timestamps.
export interface MaintenanceWindowInput {
    name: string;
    description?: string | null;
    enabled: boolean;
    kind: WindowKind;
    recurrence: WindowRecurrence;
    timezone: string;
    start_time?: string | null;
    duration_minutes?: number | null;
    days_of_week?: string[];
    starts_at?: string | null;
    ends_at?: string | null;
    scopes: MaintenanceScope[];
}

export interface HostWindowStatus {
    state: 'unrestricted' | 'in_window' | 'blocked' | 'override';
    override: { reason: string; expires_at: string; username?: string } | null;
    active_blackout: string | null;
    next_window: { id: string; name: string; starts_at: string | null } | null;
}

export const maintenanceWindowsService = {
    async list(): Promise<MaintenanceWindow[]> {
        const res = await axiosInstance.get('/api/v1/maintenance-windows');
        return res.data.windows;
    },

    async create(data: MaintenanceWindowInput): Promise<MaintenanceWindow> {
        const res = await axiosInstance.post('/api/v1/maintenance-windows', data);
        return res.data;
    },

    async update(
        id: string,
        data: MaintenanceWindowInput,
    ): Promise<MaintenanceWindow> {
        const res = await axiosInstance.put(
            `/api/v1/maintenance-windows/${id}`,
            data,
        );
        return res.data;
    },

    async remove(id: string): Promise<void> {
        await axiosInstance.delete(`/api/v1/maintenance-windows/${id}`);
    },

    async createOverride(
        hostId: string,
        reason: string,
        durationMinutes: number,
    ): Promise<void> {
        await axiosInstance.post('/api/v1/maintenance-windows/overrides', {
            host_id: hostId,
            reason,
            duration_minutes: durationMinutes,
        });
    },

    async hostStatus(hostId: string): Promise<HostWindowStatus> {
        const res = await axiosInstance.get(
            `/api/v1/maintenance-windows/host/${hostId}/status`,
        );
        return res.data;
    },
};

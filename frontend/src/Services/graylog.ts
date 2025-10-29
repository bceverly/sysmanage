import axiosInstance from './api.js';

export interface GraylogHealthResponse {
    healthy: boolean;
    version?: string;
    cluster_id?: string;
    node_id?: string;
    error?: string;
    has_gelf_tcp?: boolean;
    gelf_tcp_port?: number;
    has_syslog_tcp?: boolean;
    syslog_tcp_port?: number;
    has_syslog_udp?: boolean;
    syslog_udp_port?: number;
    has_windows_sidecar?: boolean;
    windows_sidecar_port?: number;
}

export interface GraylogAttachmentResponse {
    is_attached: boolean;
    target_hostname: string | null;
    target_ip: string | null;
    mechanism: string | null;
    port: number | null;
    detected_at: string | null;
    updated_at: string | null;
}

export async function doCheckGraylogHealth(): Promise<GraylogHealthResponse> {
    const response = await axiosInstance.get('/api/graylog/health');
    return response.data;
}

export async function doGetGraylogAttachment(hostId: string): Promise<GraylogAttachmentResponse> {
    const response = await axiosInstance.get(`/api/host/${hostId}/graylog_attachment`);
    return response.data;
}

export interface GraylogAttachRequest {
    mechanism: string;
    graylog_server: string;
    port: number;
}

export async function doAttachToGraylog(hostId: string, request: GraylogAttachRequest): Promise<{ success: boolean; message: string }> {
    const response = await axiosInstance.post(`/api/host/${hostId}/graylog/attach`, request);
    return response.data;
}

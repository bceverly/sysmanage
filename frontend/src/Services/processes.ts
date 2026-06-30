import api from './api';

export interface HostProcess {
    id: string;
    pid: number;
    parent_pid: number | null;
    process_name: string;
    username: string | null;
    status: string | null;
    cpu_percent: number | null;
    memory_percent: number | null;
    memory_rss_bytes: number | null;
    command_line: string | null;
    started_at: string | null;
    collected_at: string | null;
}

interface SimpleResult {
    result: boolean;
    message: string;
}

export const doGetHostProcesses = async (
    hostId: string,
): Promise<HostProcess[]> => {
    const response = await api.get<HostProcess[]>(
        `/api/v1/host/${hostId}/processes`,
    );
    return response.data;
};

export const doRefreshHostProcesses = async (
    hostId: string,
): Promise<SimpleResult> => {
    const response = await api.post<SimpleResult>(
        `/api/v1/host/${hostId}/processes/refresh`,
    );
    return response.data;
};

export const doKillHostProcess = async (
    hostId: string,
    pid: number,
    options: { force?: boolean; expectedName?: string } = {},
): Promise<SimpleResult> => {
    const response = await api.post<SimpleResult>(
        `/api/v1/host/${hostId}/processes/${pid}/kill`,
        {
            force: options.force ?? false,
            expected_name: options.expectedName ?? null,
        },
    );
    return response.data;
};

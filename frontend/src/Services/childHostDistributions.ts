import axiosInstance from './api.js';

export interface Distribution {
    id: string;
    child_type: string;
    distribution_name: string;
    distribution_version: string;
    display_name: string;
    install_identifier: string | null;
    executable_name: string | null;
    agent_install_method: string | null;
    agent_install_commands: string | null;
    is_active: boolean;
    min_agent_version: string | null;
    notes: string | null;
    created_at: string | null;
    updated_at: string | null;
}

export interface CreateDistributionRequest {
    child_type: string;
    distribution_name: string;
    distribution_version: string;
    display_name: string;
    install_identifier?: string;
    executable_name?: string;
    agent_install_method?: string;
    agent_install_commands?: string;
    is_active?: boolean;
    min_agent_version?: string;
    notes?: string;
}

export interface UpdateDistributionRequest {
    child_type?: string;
    distribution_name?: string;
    distribution_version?: string;
    display_name?: string;
    install_identifier?: string;
    executable_name?: string;
    agent_install_method?: string;
    agent_install_commands?: string;
    is_active?: boolean;
    min_agent_version?: string;
    notes?: string;
}

export const distributionService = {
    async getAll(childType?: string): Promise<Distribution[]> {
        const params = childType ? { child_type: childType } : {};
        const response = await axiosInstance.get('/api/child-host-distributions/all', { params });
        return response.data;
    },

    async get(id: string): Promise<Distribution> {
        const response = await axiosInstance.get(`/api/child-host-distributions/${id}`);
        return response.data;
    },

    async create(request: CreateDistributionRequest): Promise<Distribution> {
        const response = await axiosInstance.post('/api/child-host-distributions', request);
        return response.data;
    },

    async update(id: string, request: UpdateDistributionRequest): Promise<Distribution> {
        const response = await axiosInstance.put(`/api/child-host-distributions/${id}`, request);
        return response.data;
    },

    async delete(id: string): Promise<void> {
        await axiosInstance.delete(`/api/child-host-distributions/${id}`);
    },

    async toggleActive(id: string, isActive: boolean): Promise<Distribution> {
        const response = await axiosInstance.put(`/api/child-host-distributions/${id}`, {
            is_active: isActive,
        });
        return response.data;
    },
};

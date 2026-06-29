import axiosInstance from './api';

export const deployFirewall = async (hostId: string): Promise<void> => {
    await axiosInstance.post(`/api/v1/hosts/${hostId}/firewall/deploy`);
};

export const enableFirewall = async (hostId: string): Promise<void> => {
    await axiosInstance.post(`/api/v1/hosts/${hostId}/firewall/enable`);
};

export const disableFirewall = async (hostId: string): Promise<void> => {
    await axiosInstance.post(`/api/v1/hosts/${hostId}/firewall/disable`);
};

export const restartFirewall = async (hostId: string): Promise<void> => {
    await axiosInstance.post(`/api/v1/hosts/${hostId}/firewall/restart`);
};

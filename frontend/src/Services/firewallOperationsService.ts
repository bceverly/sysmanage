// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

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

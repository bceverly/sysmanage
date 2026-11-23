// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from './api';

export interface AntivirusStatus {
  id: string;
  host_id: string;
  software_name: string | null;
  install_path: string | null;
  version: string | null;
  enabled: boolean | null;
  last_updated: string;
}

export const getAntivirusStatus = async (hostId: string): Promise<AntivirusStatus | null> => {
  const response = await axiosInstance.get<AntivirusStatus | null>(`/api/v1/hosts/${hostId}/antivirus-status`);
  return response.data;
};

/** The swap SysManage added so the host clears ClamAV's memory floor. */
export const getAntivirusSwap = async (hostId: string): Promise<number | null> => {
  const response = await axiosInstance.get<{ swap_added_mb: number | null }>(`/api/v1/hosts/${hostId}/antivirus/swap`);
  return response.data.swap_added_mb ?? null;
};

/** Remove the swap file SysManage added for ClamAV. */
export const removeAntivirusSwap = async (hostId: string): Promise<void> => {
  await axiosInstance.post(`/api/v1/hosts/${hostId}/antivirus/remove-swap`);
};

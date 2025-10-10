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
  const response = await axiosInstance.get<AntivirusStatus | null>(`/api/hosts/${hostId}/antivirus-status`);
  return response.data;
};

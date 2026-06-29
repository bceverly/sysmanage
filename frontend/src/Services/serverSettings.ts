import axiosInstance from './api';

export type SettingType = 'int' | 'bool' | 'str' | 'secret';

export interface ServerSetting {
  key: string;
  group: string;
  type: SettingType;
  value: number | boolean | string;
  // Secret-typed settings only: whether a value is already stored (the value
  // itself is never sent to the client).
  configured?: boolean;
}

interface SettingsResponse {
  settings: ServerSetting[];
}

export const serverSettingsService = {
  async get(): Promise<ServerSetting[]> {
    const response = await axiosInstance.get<SettingsResponse>('/api/v1/settings');
    return response.data.settings;
  },

  async update(
    settings: Record<string, number | boolean | string>,
  ): Promise<ServerSetting[]> {
    const response = await axiosInstance.put<SettingsResponse>('/api/v1/settings', {
      settings,
    });
    return response.data.settings;
  },
};

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

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

import axiosInstance from './api.js';

export interface UpdateStatsSummary {
  total_hosts: number;
  hosts_with_updates: number;
  total_updates: number;
  security_updates: number;
  system_updates: number;
  application_updates: number;
  os_upgrades: number;
}

export interface PackageUpdate {
  id: string;
  host_id: string;
  hostname: string;
  package_name: string;
  current_version: string | null;
  available_version: string;
  package_manager: string;
  source: string | null;
  is_security_update: boolean;
  is_system_update: boolean;
  requires_reboot: boolean;
  update_size_bytes: number | null;
  status: string;
  detected_at: string;
  last_checked_at: string;
}

export interface UpdatesResponse {
  updates: PackageUpdate[];
  total_count: number;
  limit: number;
  offset: number;
}

export interface HostUpdatesResponse {
  host_id: string;
  hostname: string;
  updates: PackageUpdate[];
  total_updates: number;
  security_updates: number;
  system_updates: number;
  application_updates: number;
}

export interface UpdateResultsResponse {
  total_hosts: number;
  hosts_with_updates: number;
  total_updates: number;
  security_updates: number;
  system_updates: number;
  application_updates: number;
  results: Record<string, unknown>;
}

export interface OSUpgradeResponse {
  id: string;
  host_id: string;
  host_fqdn: string;
  host_platform: string;
  package_name: string;
  current_version: string;
  available_version: string;
  package_manager: string;
  update_type: string;
  requires_reboot: boolean;
  size_bytes: number | null;
  discovered_at: string | null;
}

export interface OSUpgradesListResponse {
  os_upgrades: OSUpgradeResponse[];
  total_count: number;
  hosts_with_upgrades: number;
}

export interface OSUpgradeSummary {
  total_hosts: number;
  hosts_with_os_upgrades: number;
  total_os_upgrades: number;
  os_upgrades_by_type: Record<string, number>;
}

class UpdatesService {

  async getUpdatesSummary(): Promise<UpdateStatsSummary> {
    try {
      const response = await axiosInstance.get('/api/updates/summary');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch updates summary:', error);
      throw error;
    }
  }

  async getAllUpdates(
    securityOnly?: boolean,
    systemOnly?: boolean,
    applicationOnly?: boolean,
    packageManager?: string,
    limit = 100,
    offset = 0
  ): Promise<UpdatesResponse> {
    try {
      const params = new window.URLSearchParams();
      if (securityOnly) params.append('security_only', 'true');
      if (systemOnly) params.append('system_only', 'true');
      if (applicationOnly) params.append('application_only', 'true');
      if (packageManager) params.append('package_manager', packageManager);
      params.append('limit', limit.toString());
      params.append('offset', offset.toString());

      const response = await axiosInstance.get(`/api/updates/?${params}`);
      return response.data;
    } catch (error) {
      console.error('Failed to fetch updates:', error);
      throw error;
    }
  }

  async getHostUpdates(
    hostId: string,
    packageManager?: string,
    securityOnly?: boolean,
    systemOnly?: boolean,
    applicationOnly?: boolean
  ): Promise<HostUpdatesResponse> {
    try {
      const params = new window.URLSearchParams();
      if (packageManager) params.append('package_manager', packageManager);
      if (securityOnly) params.append('security_only', 'true');
      if (systemOnly) params.append('system_only', 'true');
      if (applicationOnly) params.append('application_only', 'true');

      const response = await axiosInstance.get(`/api/updates/${hostId}?${params}`);
      return response.data;
    } catch (error) {
      console.error('Failed to fetch host updates:', error);
      throw error;
    }
  }

  async executeUpdates(hostIds: string[], packageNames: string[], packageManagers?: string[]): Promise<unknown> {
    try {
      const requestData = {
        host_ids: hostIds,
        package_names: packageNames,
        package_managers: packageManagers,
      };
      
      const response = await axiosInstance.post('/api/updates/execute', requestData);
      return response.data;
    } catch (error) {
      console.error('Failed to execute updates:', error);
      throw error;
    }
  }

  async getExecutionLog(hostId: string, limit = 50, offset = 0): Promise<unknown> {
    try {
      const params = new window.URLSearchParams();
      params.append('limit', limit.toString());
      params.append('offset', offset.toString());

      const response = await axiosInstance.get(`/api/updates/execution-log/${hostId}?${params}`);
      return response.data;
    } catch (error) {
      console.error('Failed to fetch execution log:', error);
      throw error;
    }
  }

  async getUpdateResults(): Promise<UpdateResultsResponse> {
    try {
      const response = await axiosInstance.get('/api/updates/summary');
      // Return the actual response data which includes update results
      return response.data;
    } catch (error) {
      console.error('Failed to fetch update results:', error);
      throw error;
    }
  }

  // OS Upgrade Methods
  async getOSUpgrades(): Promise<OSUpgradesListResponse> {
    try {
      const response = await axiosInstance.get('/api/updates/os-upgrades');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch OS upgrades:', error);
      throw error;
    }
  }

  async getOSUpgradesSummary(): Promise<OSUpgradeSummary> {
    try {
      const response = await axiosInstance.get('/api/updates/os-upgrades/summary');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch OS upgrades summary:', error);
      throw error;
    }
  }

  async executeOSUpgrades(hostIds: string[], packageManagers?: string[]): Promise<unknown> {
    try {
      const requestData = {
        host_ids: hostIds,
        package_managers: packageManagers,
      };

      const response = await axiosInstance.post('/api/updates/execute-os-upgrades', requestData);
      return response.data;
    } catch (error) {
      console.error('Failed to execute OS upgrades:', error);
      throw error;
    }
  }
}

export const updatesService = new UpdatesService();
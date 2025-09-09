import axios from 'axios';

export interface UpdateStatsSummary {
  total_hosts: number;
  hosts_with_updates: number;
  total_updates: number;
  security_updates: number;
  system_updates: number;
  application_updates: number;
}

export interface PackageUpdate {
  id: number;
  host_id: number;
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
  host_id: number;
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

class UpdatesService {
  private baseURL: string;

  constructor() {
    const config = JSON.parse(localStorage.getItem('sysmanage_config') || '{}');
    // Dynamically determine the backend URL based on current host
    const currentHost = window.location.hostname;
    const backendPort = 8080; // This should match your config file
    this.baseURL = config.apiUrl || `http://${currentHost}:${backendPort}`;
  }

  private getAuthHeaders() {
    const token = localStorage.getItem('bearer_token');
    return {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  }

  async getUpdatesSummary(): Promise<UpdateStatsSummary> {
    try {
      const response = await axios.get(`${this.baseURL}/api/updates/summary`, {
        headers: this.getAuthHeaders(),
      });
      return response.data;
    } catch (error) {
      console.error('Failed to fetch updates summary:', error);
      throw error;
    }
  }

  async getAllUpdates(
    securityOnly?: boolean,
    systemOnly?: boolean,
    packageManager?: string,
    limit = 100,
    offset = 0
  ): Promise<UpdatesResponse> {
    try {
      const params = new window.URLSearchParams();
      if (securityOnly) params.append('security_only', 'true');
      if (systemOnly) params.append('system_only', 'true');
      if (packageManager) params.append('package_manager', packageManager);
      params.append('limit', limit.toString());
      params.append('offset', offset.toString());

      const response = await axios.get(`${this.baseURL}/api/updates/?${params}`, {
        headers: this.getAuthHeaders(),
      });
      return response.data;
    } catch (error) {
      console.error('Failed to fetch updates:', error);
      throw error;
    }
  }

  async getHostUpdates(
    hostId: number,
    packageManager?: string,
    securityOnly?: boolean,
    systemOnly?: boolean
  ): Promise<HostUpdatesResponse> {
    try {
      const params = new window.URLSearchParams();
      if (packageManager) params.append('package_manager', packageManager);
      if (securityOnly) params.append('security_only', 'true');
      if (systemOnly) params.append('system_only', 'true');

      const response = await axios.get(`${this.baseURL}/api/updates/${hostId}?${params}`, {
        headers: this.getAuthHeaders(),
      });
      return response.data;
    } catch (error) {
      console.error('Failed to fetch host updates:', error);
      throw error;
    }
  }

  async executeUpdates(hostIds: number[], packageNames: string[], packageManagers?: string[]): Promise<unknown> {
    try {
      const requestData = {
        host_ids: hostIds,
        package_names: packageNames,
        package_managers: packageManagers,
      };
      
      const response = await axios.post(
        `${this.baseURL}/api/updates/execute`,
        requestData,
        {
          headers: this.getAuthHeaders(),
        }
      );
      return response.data;
    } catch (error) {
      console.error('Failed to execute updates:', error);
      throw error;
    }
  }

  async getExecutionLog(hostId: number, limit = 50, offset = 0): Promise<unknown> {
    try {
      const params = new window.URLSearchParams();
      params.append('limit', limit.toString());
      params.append('offset', offset.toString());

      const response = await axios.get(`${this.baseURL}/api/updates/execution-log/${hostId}?${params}`, {
        headers: this.getAuthHeaders(),
      });
      return response.data;
    } catch (error) {
      console.error('Failed to fetch execution log:', error);
      throw error;
    }
  }

  async getUpdateResults(): Promise<UpdateResultsResponse> {
    try {
      const response = await axios.get(`${this.baseURL}/api/updates/summary`, {
        headers: this.getAuthHeaders(),
      });
      // Return the actual response data which includes update results
      return response.data;
    } catch (error) {
      console.error('Failed to fetch update results:', error);
      throw error;
    }
  }
}

export const updatesService = new UpdatesService();
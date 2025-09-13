import axiosInstance from './api.js';

export interface Script {
  id?: number;
  name: string;
  description: string;
  content: string;
  shell_type: string;
  platform?: string;
  run_as_user?: string;
  is_active: boolean;
  created_by?: number;
  created_at?: string;
  updated_at?: string;
}

export interface ScriptExecution {
  id: number;
  script_id?: number;
  host_id: number;
  host_fqdn: string;
  script_name: string;
  script_content: string;
  shell_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'timeout';
  requested_by: number;
  started_at?: string;
  completed_at?: string;
  exit_code?: number;
  execution_time?: number;
  stdout_output?: string;
  stderr_output?: string;
  error_message?: string;
}

export interface Host {
  id: number;
  fqdn: string;
  status: string;
  active: boolean;
  approval_status: string;
  last_access: string;
  platform?: string;
  script_execution_enabled?: boolean;
  enabled_shells?: string;
}

export interface ExecuteScriptRequest {
  host_id: number;
  saved_script_id?: number;
  script_name?: string;
  script_content?: string;
  shell_type?: string;
}

export interface ScriptExecutionResponse {
  message: string;
  execution_id: string;
}

export const scriptsService = {
  // Saved scripts management
  async getSavedScripts(): Promise<Script[]> {
    const response = await axiosInstance.get('/api/scripts/');
    return response.data;
  },

  async createScript(script: Omit<Script, 'id' | 'created_by' | 'created_at' | 'updated_at'>): Promise<Script> {
    const response = await axiosInstance.post('/api/scripts/', script);
    return response.data;
  },

  async updateScript(id: number, script: Partial<Script>): Promise<Script> {
    const response = await axiosInstance.put(`/api/scripts/${id}`, script);
    return response.data;
  },

  async deleteScript(id: number): Promise<void> {
    await axiosInstance.delete(`/api/scripts/${id}`);
  },

  async getScript(id: number): Promise<Script> {
    const response = await axiosInstance.get(`/api/scripts/${id}`);
    return response.data;
  },

  // Script execution
  async executeScript(executeRequest: ExecuteScriptRequest): Promise<ScriptExecutionResponse> {
    const response = await axiosInstance.post('/api/scripts/execute', executeRequest);
    return response.data;
  },

  // Script executions history
  async getScriptExecutions(page: number = 1, limit: number = 50): Promise<{
    executions: ScriptExecution[];
    total: number;
    page: number;
    pages: number;
  }> {
    const response = await axiosInstance.get('/api/scripts/executions/', {
      params: { page, limit }
    });
    return response.data;
  },

  async getScriptExecution(id: string | number): Promise<ScriptExecution> {
    const response = await axiosInstance.get(`/api/scripts/executions/${id}`);
    return response.data;
  },

  async deleteScriptExecution(id: string | number): Promise<void> {
    await axiosInstance.delete(`/api/scripts/executions/${id}`);
  },

  async deleteScriptExecutionsBulk(executionIds: (string | number)[]): Promise<void> {
    // Convert all IDs to strings to match backend expectation
    const stringIds = executionIds.map(id => String(id));
    console.log('Sending bulk delete request for execution IDs:', stringIds);
    await axiosInstance.request({
      method: 'DELETE',
      url: '/api/scripts/executions/bulk',
      data: stringIds
    });
  },

  // Hosts (for host selection)
  async getActiveHosts(): Promise<Host[]> {
    const response = await axiosInstance.get('/hosts');
    // Filter for approved hosts that are either active or currently up
    return response.data.filter((host: Host) => 
      host.approval_status === 'approved' && (host.active === true || host.status === 'up')
    );
  }
};
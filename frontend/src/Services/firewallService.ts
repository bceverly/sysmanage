import axiosInstance from './api';

export interface PortWithProtocols {
  port: string;
  protocols: string[];
}

export interface FirewallStatus {
  id: string;
  host_id: string;
  firewall_name: string | null;
  enabled: boolean;
  tcp_open_ports: string | null;  // Legacy
  udp_open_ports: string | null;  // Legacy
  ipv4_ports: string | null;  // JSON string of PortWithProtocols[]
  ipv6_ports: string | null;  // JSON string of PortWithProtocols[]
  last_updated: string;
}

export const getFirewallStatus = async (hostId: string): Promise<FirewallStatus | null> => {
  const response = await axiosInstance.get<FirewallStatus | null>(`/api/hosts/${hostId}/firewall-status`);
  return response.data;
};

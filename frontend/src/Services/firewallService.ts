// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

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
  const response = await axiosInstance.get<FirewallStatus | null>(`/api/v1/hosts/${hostId}/firewall-status`);
  return response.data;
};

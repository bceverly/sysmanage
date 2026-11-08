// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Agent mutual TLS settings (ROADMAP 25.10): the rollout mode and where the
// fleet stands.

import axiosInstance from './api';

export type AgentCertificateMode = 'off' | 'optional' | 'enforced';

export interface HostNotReady {
  id: string;
  fqdn: string;
  status: string;
}

export interface AgentCertificateFleet {
  approved: number;
  presenting: number;
  not_presenting: number;
  expiring: number;
  expired: number;
  not_ready: HostNotReady[];
}

export interface AgentCertificateSettings {
  mode: AgentCertificateMode;
  modes: AgentCertificateMode[];
  fleet: AgentCertificateFleet;
}

const PATH = '/api/v1/agent-certificates';

export const agentCertificatesService = {
  async get(): Promise<AgentCertificateSettings> {
    return (await axiosInstance.get<AgentCertificateSettings>(PATH)).data;
  },

  /** 409 ``hosts_not_presenting`` when enforcing would cut hosts off; pass
   *  ``force`` once the operator has confirmed. */
  async setMode(mode: AgentCertificateMode, force = false): Promise<AgentCertificateSettings> {
    return (await axiosInstance.put<AgentCertificateSettings>(PATH, { mode, force })).data;
  },
};

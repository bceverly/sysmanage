// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Old kernels and unneeded packages on one host (ROADMAP 27.8).
import axiosInstance from './api.js';

export interface CleanupItem {
  name: string;
  kernel: string | null;
  reason: string; // old_kernel | unneeded | protected
}

export interface CleanupRun {
  id: string;
  mode: 'plan' | 'apply';
  status: string; // queued planned done refused failed unsupported boot_path_broken
  trigger: string;
  requested_by: string | null;
  protected: { release: string; reason: string }[];
  approved: string[] | null;
  packages: CleanupItem[];
  kept: CleanupItem[];
  running_kernel: string | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface CleanupState {
  running_kernel: string | null;
  installed_kernels: string[];
  proven_kernels: string[];
  protected: { release: string; reason: string }[];
  refusal: string | null;
  runs: CleanupRun[];
}

export const packageCleanupService = {
  async state(hostId: string): Promise<CleanupState> {
    return (await axiosInstance.get(`/api/v1/host/${hostId}/cleanup`)).data;
  },
  async plan(hostId: string): Promise<CleanupRun> {
    return (await axiosInstance.post(`/api/v1/host/${hostId}/cleanup/plan`)).data;
  },
  async apply(hostId: string, packages: string[]): Promise<CleanupRun> {
    return (await axiosInstance.post(`/api/v1/host/${hostId}/cleanup/apply`, { packages })).data;
  },
};

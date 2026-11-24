// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Fleet restore jobs (ROADMAP 27.2, Enterprise backup_ops_engine): one
// restore asked of many hosts, released in waves, each host from its own
// newest snapshot or its newest taken before a moment.  402 without the engine.

import axiosInstance from './api';

const base = '/api/v1/backups/fleet-restores';

export interface FleetRestoreTarget {
  host_id: string;
  fqdn: string | null;
  /** waiting / running / ok / failed / skipped / canceled */
  status: string;
  snapshot: string | null;
  run_id: string | null;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface FleetRestore {
  id: string;
  name: string;
  /** awaiting_approval / running / completed / canceled / rejected */
  status: string;
  include: string[];
  exclude: string[];
  before: string | null;
  in_place: boolean;
  dry_run: boolean;
  concurrency: number;
  created_by: string;
  created_at: string | null;
  approved_by: string | null;
  finished_at: string | null;
  hosts: number;
  counts: Record<string, number>;
  targets?: FleetRestoreTarget[];
}

export interface FleetRestoreRequest {
  name: string;
  host_ids: string[];
  include: string[];
  exclude: string[];
  before: string | null;
  in_place: boolean;
  acknowledge_in_place: boolean;
  dry_run: boolean;
  acknowledge_unsigned: boolean;
  concurrency: number;
}

export const listFleetRestores = async (): Promise<FleetRestore[]> =>
  (await axiosInstance.get<{ jobs: FleetRestore[] }>(base)).data.jobs;

export const getFleetRestore = async (id: string): Promise<FleetRestore> =>
  (await axiosInstance.get<FleetRestore>(`${base}/${id}`)).data;

export const createFleetRestore = async (body: FleetRestoreRequest): Promise<FleetRestore> =>
  (await axiosInstance.post<FleetRestore>(base, body)).data;

export const cancelFleetRestore = async (id: string): Promise<FleetRestore> =>
  (await axiosInstance.post<FleetRestore>(`${base}/${id}/cancel`)).data;

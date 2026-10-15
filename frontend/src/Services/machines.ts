// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Machines and asset tags (Phase 23.2).  A host is one OS; a machine is the
// hardware under it, shared by every OS on a multi-boot machine.  The asset tag
// lives on the machine.  Refusals come back as codes (``detail.code``), which
// the UI translates.

import axiosInstance from "./api";

/** Per-source outcome of reading the hardware identity on the host. */
export type IdentitySourceStatus = "ran" | "absent" | "unprivileged" | "failed" | "placeholder";

export interface MachineSummary {
  id: string;
  system_uuid: string | null;
  system_serial: string | null;
  board_serial: string | null;
  vendor: string | null;
  model: string | null;
  is_virtual: boolean;
  asset_tag: string | null;
}

export interface HostBrief {
  id: string;
  fqdn: string;
  platform: string | null;
  active: boolean;
}

export interface HostMachine {
  identity: {
    system_uuid: string | null;
    system_serial: string | null;
    board_serial: string | null;
    status: Partial<Record<"system_uuid" | "system_serial" | "board_serial", IdentitySourceStatus>>;
    reported_at: string | null;
  };
  machine: MachineSummary | null;
  other_hosts: HostBrief[];
  /** ``reason``: ``virtual_clone`` | ``serial_mismatch`` */
  conflict: { reason: string; machine: MachineSummary | null } | null;
}

export interface MachineConflict {
  host: HostBrief;
  /** ``virtual_clone`` | ``serial_mismatch`` */
  reason: string;
  machine: MachineSummary | null;
}

export type SchemeMode = "builder" | "regex";

export interface AssetTagScheme {
  mode: SchemeMode;
  prefix: string;
  separator: string;
  digits: number;
  suffix: string;
  pattern: string;
  enforce: boolean;
}

export interface SchemeReport {
  scheme: AssetTagScheme;
  /** A sample tag (number 42) in builder mode; null in regex mode. */
  preview: string | null;
  examples: { pass: string[]; fail: string[] };
  next_free: string | null;
  tagged: number;
  /** Existing tags the scheme rejects -- reported, never rewritten. */
  nonconforming: string[];
}

export const SEPARATORS = ["", "-", "_", "."] as const;
export const MIN_DIGITS = 1;
export const MAX_DIGITS = 12;

export const getHostMachine = async (hostId: string): Promise<HostMachine> =>
  (await axiosInstance.get<HostMachine>(`/api/v1/host/${hostId}/machine`)).data;

export const getMachineConflicts = async (): Promise<MachineConflict[]> =>
  (await axiosInstance.get<{ conflicts: MachineConflict[] }>("/api/v1/machines/conflicts"))
    .data.conflicts;

export const resolveMachineConflict = async (
  hostId: string,
  decision: "same" | "different",
): Promise<MachineSummary> =>
  (
    await axiosInstance.post<{ machine: MachineSummary }>(
      `/api/v1/host/${hostId}/machine/resolve`,
      { decision },
    )
  ).data.machine;

export const getAssetTagScheme = async (): Promise<SchemeReport> =>
  (await axiosInstance.get<SchemeReport>("/api/v1/asset-tags/scheme")).data;

/** What a DRAFT scheme would do; saves nothing. */
export const previewAssetTagScheme = async (scheme: AssetTagScheme): Promise<SchemeReport> =>
  (await axiosInstance.post<SchemeReport>("/api/v1/asset-tags/scheme/preview", scheme)).data;

export const saveAssetTagScheme = async (scheme: AssetTagScheme): Promise<SchemeReport> =>
  (await axiosInstance.put<SchemeReport>("/api/v1/asset-tags/scheme", scheme)).data;

/**
 * Entry-time check: fits the scheme, and is not another machine's tag.
 * ``reason`` (why a tag was refused): ``empty`` | ``too_long`` |
 * ``bad_characters`` | ``does_not_match_scheme`` | ``scheme_timeout`` |
 * ``duplicate``.
 */
export const checkAssetTag = async (
  tag: string,
  machineId?: string,
): Promise<{ ok: boolean; reason: string | null }> =>
  (
    await axiosInstance.get<{ ok: boolean; reason: string | null }>(
      "/api/v1/asset-tags/check",
      { params: machineId ? { tag, machine_id: machineId } : { tag } },
    )
  ).data;

/** Set or change the machine's tag; ``null`` clears it. */
export const setMachineAssetTag = async (
  machineId: string,
  assetTag: string | null,
): Promise<{ machine_id: string; asset_tag: string | null }> =>
  (
    await axiosInstance.put<{ machine_id: string; asset_tag: string | null }>(
      `/api/v1/machine/${machineId}/asset-tag`,
      { asset_tag: assetTag },
    )
  ).data;

/** The refusal code in an axios error, if the server sent one. */
export const errorCode = (error: unknown): string | null => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detail && typeof detail === "object" && "code" in detail) {
    return String(detail.code);
  }
  return null;
};

// --- CSV import / export and held tags (Phase 23.2 S5) ---------------------

/** What one CSV row will do; ``reason`` is a code the UI translates. */
export type ImportStatus =
  | 'assign'
  | 'unchanged'
  | 'hold'
  | 'fails_scheme'
  | 'duplicate'
  | 'ambiguous'
  | 'invalid'
  | 'skipped';

export interface ImportRow {
  line: number;
  asset_tag: string;
  system_uuid: string;
  system_serial: string;
  status: ImportStatus;
  reason: string | null;
  machine_id: string | null;
  /** The machine's (or the hold's) tag before this row. */
  previous: string | null;
  hosts: string[];
  /** MAC of a bare-metal box discovery saw with this serial. */
  discovered_mac: string | null;
}

export interface ImportResult {
  rows: ImportRow[];
  summary: Partial<Record<ImportStatus, number>>;
}

export interface HeldTag {
  id: string;
  kind: 'system_uuid' | 'system_serial';
  identifier: string;
  asset_tag: string;
  created_at: string | null;
  created_by: string | null;
}

/** A dry run of the file: what every row would do.  Writes nothing. */
export const previewAssetTagImport = async (csv: string): Promise<ImportResult> =>
  (await axiosInstance.post<ImportResult>('/api/v1/asset-tags/import/preview', { csv })).data;

/** Re-plans the file on the server and writes its assign / hold rows. */
export const applyAssetTagImport = async (csv: string): Promise<ImportResult> =>
  (await axiosInstance.post<ImportResult>('/api/v1/asset-tags/import/apply', { csv })).data;

export const exportAssetTags = async (): Promise<Blob> =>
  (await axiosInstance.get<Blob>('/api/v1/asset-tags/export', { responseType: 'blob' })).data;

export const getHeldTags = async (): Promise<HeldTag[]> =>
  (await axiosInstance.get<{ held: HeldTag[] }>('/api/v1/asset-tags/held')).data.held;

export const releaseHeldTag = async (id: string): Promise<void> => {
  await axiosInstance.delete(`/api/v1/asset-tags/held/${id}`);
};

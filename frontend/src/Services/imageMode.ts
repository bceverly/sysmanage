// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Image-mode host management API client (Phase 17.3).
 *
 * Wraps the ``/api/v1/image-mode/host/{host_id}/*`` endpoints for bootc /
 * rpm-ostree image-mode hosts.  Every call returns 402 when the Enterprise
 * ``image_mode_engine`` module isn't loaded; the caller is expected to gate
 * its UI on ``isModuleLicensed("image_mode_engine")`` rather than rely on
 * per-call error handling.  A 400 is returned when the host isn't image-mode
 * and a 404 for an unknown host.
 */

import axiosInstance from './api';

// Server-issued host IDs get interpolated into request URL paths.  Reject
// anything that isn't a plain id token first, so tainted input cannot
// manipulate the path (SonarCloud S7044 / S8476).
const safeId = (value: string): string => {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) {
    throw new Error(`Invalid identifier: ${value}`);
  }
  return value;
};

export interface ImageModeActionResponse {
  result: boolean;
  action: string;
  message_id: string;
}

/**
 * Stage a new image on an image-mode host (does NOT reboot).  When
 * ``targetRef`` is omitted the backend stages the host's default/next image.
 */
export const stageImage = async (
  hostId: string,
  targetRef?: string,
): Promise<ImageModeActionResponse> => {
  const r = await axiosInstance.post<ImageModeActionResponse>(
    `/api/v1/image-mode/host/${safeId(hostId)}/stage`,
    targetRef ? { target_ref: targetRef } : {},
  );
  return r.data;
};

/** Apply the staged image on an image-mode host.  REBOOTS the host. */
export const applyImage = async (
  hostId: string,
): Promise<ImageModeActionResponse> => {
  const r = await axiosInstance.post<ImageModeActionResponse>(
    `/api/v1/image-mode/host/${safeId(hostId)}/apply`,
  );
  return r.data;
};

/** Roll back to the prior image on an image-mode host.  REBOOTS the host. */
export const rollbackImage = async (
  hostId: string,
): Promise<ImageModeActionResponse> => {
  const r = await axiosInstance.post<ImageModeActionResponse>(
    `/api/v1/image-mode/host/${safeId(hostId)}/rollback`,
  );
  return r.data;
};

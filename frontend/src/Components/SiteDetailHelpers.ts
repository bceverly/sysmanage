// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Pure helpers, types, and constants extracted from SiteDetail.tsx to
 * keep the page component small.  No React state or hooks here — just
 * formatting utilities and the page's local state shape.
 */

import { FederationSiteDetail } from "../Services/federation";

export function statusChipColor(
  status: FederationSiteDetail["status"],
): "success" | "warning" | "error" | "default" {
  switch (status) {
    case "enrolled":
      return "success";
    case "pending":
      return "warning";
    case "suspended":
      return "error";
    default:
      return "default";
  }
}

export function formatAbsolute(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

/** Locale-aware "N minutes ago" via the browser's Intl, no hardcoded units. */
export function formatRelative(
  iso: string | null | undefined,
  locale: string,
): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const diffSec = Math.round((then - Date.now()) / 1000);
  const abs = Math.abs(diffSec);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (abs < 60) return rtf.format(Math.round(diffSec), "second");
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
  return rtf.format(Math.round(diffSec / 86400), "day");
}

export type SyncHealth = "healthy" | "stale" | "overdue" | "unknown";

/** Classify connection health by comparing last-sync age to the expected
 * interval: within 2× = healthy, 2–4× = stale, beyond (or never) = overdue. */
export function syncHealth(
  lastSyncIso: string | null | undefined,
  intervalSeconds: number | undefined,
): SyncHealth {
  if (!lastSyncIso) return "unknown";
  const then = new Date(lastSyncIso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const ageSec = (Date.now() - then) / 1000;
  const interval = intervalSeconds && intervalSeconds > 0 ? intervalSeconds : 300;
  if (ageSec <= interval * 2) return "healthy";
  if (ageSec <= interval * 4) return "stale";
  return "overdue";
}

export const SYNC_HEALTH_COLOR: Record<
  SyncHealth,
  "success" | "warning" | "error" | "default"
> = {
  healthy: "success",
  stale: "warning",
  overdue: "error",
  unknown: "default",
};

export interface SiteDetailState {
  loading: boolean;
  licensed: boolean | null;
  site: FederationSiteDetail | null;
  notFound: boolean;
  error: string | null;
}

export const initialState: SiteDetailState = {
  loading: true,
  licensed: null,
  site: null,
  notFound: false,
  error: null,
};

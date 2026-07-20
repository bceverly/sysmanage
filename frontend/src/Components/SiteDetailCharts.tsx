// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Dependency-free SVG chart primitives for the SiteDetail sync-status
 * timeline.  Extracted from SiteDetail.tsx; purely presentational, no
 * hooks or state.
 */

import React from "react";

/** Dependency-free SVG sparkline for the sync-status timeline.  Plots a
 * numeric series left-to-right; failed points are dropped to null so the
 * line breaks rather than spiking to zero.  Returns null for an empty
 * series so the caller can render an empty-state instead. */
export function Sparkline({
  values,
  width = 280,
  height = 48,
  color = "#1976d2",
  testId,
}: Readonly<{
  values: (number | null)[];
  width?: number;
  height?: number;
  color?: string;
  testId?: string;
}>) {
  const present = values.filter((v): v is number => v !== null);
  if (present.length === 0) return null;
  const max = Math.max(...present);
  const min = Math.min(...present);
  const span = max - min || 1;
  const stepX = values.length > 1 ? width / (values.length - 1) : 0;
  const points = values
    .map((v, i) => {
      if (v === null) return null;
      const x = i * stepX;
      // Invert Y so larger values sit higher on the chart.
      const y = height - ((v - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter((p): p is string => p !== null)
    .join(" ");
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      data-testid={testId}
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Dependency-free SVG histogram of upstream-sync success vs. failure over
 * time.  Buckets the timeline into equal time intervals and draws a stacked
 * bar per bucket (success green on the bottom, failures red on top) so an
 * operator can see at a glance whether a site's uplink has been flapping.
 * Returns null for an empty series so the caller can render an empty-state. */
export function SyncHealthHistogram({
  events,
  width = 280,
  height = 60,
  buckets = 12,
  testId,
}: Readonly<{
  events: ReadonlyArray<{ recorded_at: string | null; sync_status: string }>;
  width?: number;
  height?: number;
  buckets?: number;
  testId?: string;
}>) {
  const points = events
    .map((e) => ({
      t: e.recorded_at ? new Date(e.recorded_at).getTime() : Number.NaN,
      ok: e.sync_status === "success",
    }))
    .filter((p) => !Number.isNaN(p.t));
  if (points.length === 0) return null;

  const tMin = Math.min(...points.map((p) => p.t));
  const tMax = Math.max(...points.map((p) => p.t));
  const tSpan = tMax - tMin || 1;
  const n = Math.max(1, buckets);
  // Each bucket's start timestamp is a stable, unique identity (tSpan >= 1,
  // so every slice start differs) — used as the React key instead of the
  // array index.
  const bucketMs = tSpan / n;
  const agg = Array.from({ length: n }, (_, i) => ({
    startT: tMin + bucketMs * i,
    ok: 0,
    fail: 0,
  }));
  for (const p of points) {
    let idx = Math.floor(((p.t - tMin) / tSpan) * n);
    if (idx >= n) idx = n - 1; // the latest point lands in the final bucket
    if (p.ok) agg[idx].ok += 1;
    else agg[idx].fail += 1;
  }
  const maxTotal = Math.max(1, ...agg.map((b) => b.ok + b.fail));
  const gap = 2;
  const barW = (width - gap * (n - 1)) / n;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      data-testid={testId}
    >
      {agg.map((b, i) => {
        const x = i * (barW + gap);
        const okH = (b.ok / maxTotal) * height;
        const failH = (b.fail / maxTotal) * height;
        return (
          <g key={`bucket-${b.startT}`}>
            {b.ok > 0 && (
              <rect
                x={x}
                y={height - okH}
                width={barW}
                height={okH}
                fill="#2e7d32"
              />
            )}
            {b.fail > 0 && (
              <rect
                x={x}
                y={height - okH - failH}
                width={barW}
                height={failH}
                fill="#d32f2f"
              />
            )}
          </g>
        );
      })}
    </svg>
  );
}

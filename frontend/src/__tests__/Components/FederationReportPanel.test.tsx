// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

// `t` and the returned object MUST be stable across renders (the real
// react-i18next memoises them) — a fresh `t` per call breaks downstream
// useCallback/useEffect deps into an infinite render loop.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = fallback || key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  const value = { t, i18n: { language: "en" } };
  return { useTranslation: () => value };
});

vi.mock("../../Services/federation", () => ({
  doListFederationSites: vi.fn(),
  doGetFederationCrossSiteReport: vi.fn(),
}));

import * as fed from "../../Services/federation";
import FederationReportPanel from "../../Components/FederationReportPanel";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => vi.clearAllMocks());

test("renders the Enterprise upsell when unlicensed", async () => {
  m(fed.doListFederationSites).mockResolvedValue({ licensed: false });
  render(<FederationReportPanel />);
  expect(
    await screen.findByTestId("federation-report-upsell"),
  ).toBeTruthy();
});

test("generates a cross-site report with per-site rows and totals", async () => {
  m(fed.doListFederationSites).mockResolvedValue({
    licensed: true,
    sites: [
      { id: "s1", name: "Alpha", url: "https://a", status: "enrolled", host_count: 10 },
      { id: "s2", name: "Beta", url: "https://b", status: "enrolled", host_count: 5 },
    ],
  });
  m(fed.doGetFederationCrossSiteReport).mockResolvedValue({
    licensed: true,
    sites: [
      {
        site_id: "s1",
        site_name: "Alpha",
        host_count: 10,
        active_count: 8,
        worst_compliance: { baseline: "STIG", score_percent: 61 },
        critical_count: 2,
        high_count: 3,
        medium_count: 0,
        low_count: 0,
        last_sync_at: null,
      },
    ],
    totals: {
      site_count: 1,
      host_count: 10,
      active_count: 8,
      critical_count: 2,
      high_count: 3,
      medium_count: 0,
      low_count: 0,
    },
  });
  render(<FederationReportPanel />);
  // Wait for the site list to load, then generate.
  await screen.findByTestId("federation-report-generate");
  fireEvent.click(screen.getByTestId("federation-report-generate"));
  await waitFor(() =>
    expect(m(fed.doGetFederationCrossSiteReport)).toHaveBeenCalledWith([]),
  );
  expect(await screen.findByTestId("federation-report-table")).toBeTruthy();
  expect(screen.getByText("Alpha")).toBeTruthy();
  expect(screen.getByText("STIG 61%")).toBeTruthy();
  expect(screen.getByTestId("federation-report-totals")).toBeTruthy();
  expect(screen.getByText(/Totals \(1 sites\)/i)).toBeTruthy();
});

test("an empty report renders no table until generated", async () => {
  m(fed.doListFederationSites).mockResolvedValue({ licensed: true, sites: [] });
  render(<FederationReportPanel />);
  await screen.findByTestId("federation-report-generate");
  expect(screen.queryByTestId("federation-report-table")).toBeNull();
});

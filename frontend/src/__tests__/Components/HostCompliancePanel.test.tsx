// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- this panel's loader lists `t` in
// its deps.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

// Render the action cells so the scan/dispatch buttons are reachable; the
// real grid's CSS-var shorthand trips jsdom's cssstyle.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
  }: { rows?: any[]; columns?: any[] }) => (
    <div data-testid="grid">
      {(rows ?? []).map((row, i) => (
        <div key={String(row.id ?? i)} data-testid="row">
          {(columns ?? []).map((c) => (
            <span key={c.field}>
              {(() => {
                if (c.renderCell) return c.renderCell({ row, value: row[c.field] });
                if (c.valueGetter) return String(c.valueGetter(row[c.field], row) ?? "");
                return String(row[c.field] ?? "");
              })()}
            </span>
          ))}
        </div>
      ))}
    </div>
  ),
  GridRenderCellParams: {},
}));

// A Pro+/air-gap-only card that hides itself elsewhere; not this test's subject.
vi.mock("../../Components/AirgapComplianceBucketsCard", () => ({
  default: () => <div data-testid="buckets" />,
}));

vi.mock("../../Services/packageProfiles", async (orig) => {
  const actual =
    await orig<typeof import("../../Services/packageProfiles")>();
  return {
    ...actual,
    packageProfilesService: {
      list: vi.fn(),
      statusForHost: vi.fn(),
      scanHost: vi.fn(),
      dispatchToAgent: vi.fn(),
    },
  };
});

import { packageProfilesService } from "../../Services/packageProfiles";
import HostCompliancePanel from "../../Components/HostCompliancePanel";

const PROFILE = {
  id: "p1",
  name: "Baseline",
  description: null,
  enabled: true,
  constraints: [],
  created_at: null,
  updated_at: null,
};

const STATUS = {
  id: "s1",
  host_id: "h1",
  profile_id: "p1",
  status: "NON_COMPLIANT" as const,
  violations: [{ package_name: "telnet", reason: "BLOCKED" }],
  last_scan_at: "2026-08-01T00:00:00Z",
};

describe("HostCompliancePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(packageProfilesService.list).mockResolvedValue([PROFILE]);
    vi.mocked(packageProfilesService.statusForHost).mockResolvedValue([]);
    vi.mocked(packageProfilesService.scanHost).mockResolvedValue(STATUS);
    vi.mocked(packageProfilesService.dispatchToAgent).mockResolvedValue({
      status: "queued",
    });
  });

  afterEach(() => vi.restoreAllMocks());

  test("renders the profile row once loaded", async () => {
    render(<HostCompliancePanel hostId="h1" />);
    expect(await screen.findByText("Baseline")).toBeInTheDocument();
  });

  test("renders the no-profiles notice when none exist", async () => {
    vi.mocked(packageProfilesService.list).mockResolvedValue([]);
    render(<HostCompliancePanel hostId="h1" />);
    expect(
      await screen.findByText(
        "No compliance profiles defined. Create one in Settings → Compliance Profiles.",
      ),
    ).toBeInTheDocument();
  });

  test("reports a load failure", async () => {
    vi.mocked(packageProfilesService.list).mockRejectedValue(new Error("down"));
    render(<HostCompliancePanel hostId="h1" />);
    expect(
      await screen.findByText("Failed to load compliance data"),
    ).toBeInTheDocument();
  });

  test("a profile never scanned shows the not-scanned chip", async () => {
    render(<HostCompliancePanel hostId="h1" />);
    expect(await screen.findByText("Not Scanned")).toBeInTheDocument();
  });

  test("scanning reports the resulting status and violation count", async () => {
    render(<HostCompliancePanel hostId="h1" />);
    await screen.findByText("Baseline");
    fireEvent.click(screen.getByRole("button", { name: /^Scan$/ }));
    await waitFor(() =>
      expect(packageProfilesService.scanHost).toHaveBeenCalledWith("p1", "h1"),
    );
    expect(
      await screen.findByText("Scan complete: NON_COMPLIANT (1 violation(s))"),
    ).toBeInTheDocument();
  });

  test("surfaces the server's detail when a scan fails", async () => {
    vi.mocked(packageProfilesService.scanHost).mockRejectedValue({
      response: { data: { detail: "no inventory cached" } },
    });
    render(<HostCompliancePanel hostId="h1" />);
    await screen.findByText("Baseline");
    fireEvent.click(screen.getByRole("button", { name: /^Scan$/ }));
    expect(
      await screen.findByText("no inventory cached"),
    ).toBeInTheDocument();
  });

  test("falls back to a generic message when a scan failure has no detail", async () => {
    vi.mocked(packageProfilesService.scanHost).mockRejectedValue(
      new Error("boom"),
    );
    render(<HostCompliancePanel hostId="h1" />);
    await screen.findByText("Baseline");
    fireEvent.click(screen.getByRole("button", { name: /^Scan$/ }));
    expect(await screen.findByText("Scan failed")).toBeInTheDocument();
  });

  test("dispatching a live scan asks the agent", async () => {
    render(<HostCompliancePanel hostId="h1" />);
    await screen.findByText("Baseline");
    fireEvent.click(screen.getByRole("button", { name: /^Live Scan$/ }));
    await waitFor(() =>
      expect(packageProfilesService.dispatchToAgent).toHaveBeenCalledWith(
        "p1",
        "h1",
      ),
    );
    expect(
      await screen.findByText(
        "Live-scan dispatched to agent — result will arrive shortly",
      ),
    ).toBeInTheDocument();
  });

  test("reports a failed dispatch", async () => {
    vi.mocked(packageProfilesService.dispatchToAgent).mockRejectedValue(
      new Error("offline"),
    );
    render(<HostCompliancePanel hostId="h1" />);
    await screen.findByText("Baseline");
    fireEvent.click(screen.getByRole("button", { name: /^Live Scan$/ }));
    expect(
      await screen.findByText("Failed to dispatch live scan"),
    ).toBeInTheDocument();
  });
});

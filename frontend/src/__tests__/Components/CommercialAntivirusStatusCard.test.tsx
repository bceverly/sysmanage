// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, act } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(`{{${k}}}`, String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/commercialAntivirusService", () => ({
  getCommercialAntivirusStatus: vi.fn(),
}));

vi.mock("../../utils/locale", () => ({ appLocale: () => "en-US" }));

import { getCommercialAntivirusStatus } from "../../Services/commercialAntivirusService";
import CommercialAntivirusStatusCard from "../../Components/CommercialAntivirusStatusCard";

const mockGet = vi.mocked(getCommercialAntivirusStatus);

const FULL = {
  id: "c1",
  host_id: "h1",
  product_name: "Windows Defender",
  product_version: "4.18.1",
  service_enabled: true,
  antispyware_enabled: false,
  antivirus_enabled: true,
  realtime_protection_enabled: null,
  full_scan_age: 0,
  quick_scan_age: 1,
  full_scan_end_time: "2026-03-01T10:00:00",
  quick_scan_end_time: null,
  signature_last_updated: "2026-03-02T11:00:00Z",
  signature_version: "1.400.1",
  tamper_protection_enabled: true,
  created_at: "2026-03-01T00:00:00Z",
  last_updated: "2026-03-03T12:00:00",
};

const loc = (iso: string) => new Date(iso).toLocaleString("en-US");

describe("CommercialAntivirusStatusCard", () => {
  let errSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    errSpy = vi.spyOn(window.console, "error").mockImplementation(() => {});
    mockGet.mockResolvedValue(FULL);
  });

  afterEach(() => {
    errSpy.mockRestore();
    vi.useRealTimers();
  });

  test("renders full product, protection and scan details", async () => {
    render(<CommercialAntivirusStatusCard hostId="h1" />);
    expect(await screen.findByText("Windows Defender")).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("h1");
    expect(screen.getByText("Version: 4.18.1")).toBeInTheDocument();
    expect(screen.getByText("Protected")).toBeInTheDocument();
    expect(screen.getByText("Core Service: Enabled")).toBeInTheDocument();
    expect(screen.getByText("Antispyware: Disabled")).toBeInTheDocument();
    expect(screen.getByText("Real-time Protection: Unknown")).toBeInTheDocument();
    expect(screen.getByText("Last Full Scan: Today")).toBeInTheDocument();
    expect(screen.getByText("Last Quick Scan: Yesterday")).toBeInTheDocument();
    expect(screen.getByText(loc("2026-03-01T10:00:00Z"))).toBeInTheDocument();
    expect(screen.getByText("Version: 1.400.1")).toBeInTheDocument();
    expect(
      screen.getByText(`Last Updated: ${loc("2026-03-02T11:00:00Z")}`),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`Status last updated: ${loc("2026-03-03T12:00:00Z")}`),
    ).toBeInTheDocument();
  });

  test("shows not-protected and the scan-age variants", async () => {
    mockGet.mockResolvedValue({
      ...FULL,
      antivirus_enabled: false,
      product_version: null,
      full_scan_age: 4294967295,
      quick_scan_age: 12,
      full_scan_end_time: null,
      signature_version: null,
      signature_last_updated: null,
    });
    render(<CommercialAntivirusStatusCard hostId="h1" />);
    expect(await screen.findByText("Not Protected")).toBeInTheDocument();
    expect(screen.getByText("Last Full Scan: Never")).toBeInTheDocument();
    expect(screen.getByText("Last Quick Scan: 12 days ago")).toBeInTheDocument();
    expect(screen.queryByText(/^Version:/)).toBeNull();
    expect(screen.queryByText(/^Last Updated:/)).toBeNull();
  });

  test("unknown scan ages render N/A", async () => {
    mockGet.mockResolvedValue({ ...FULL, full_scan_age: null, quick_scan_age: null });
    render(<CommercialAntivirusStatusCard hostId="h1" />);
    expect(await screen.findByText("Last Full Scan: N/A")).toBeInTheDocument();
    expect(screen.getByText("Last Quick Scan: N/A")).toBeInTheDocument();
  });

  test("shows the empty state when no product is detected", async () => {
    mockGet.mockResolvedValue(null);
    render(<CommercialAntivirusStatusCard hostId="h1" />);
    expect(
      await screen.findByText("No commercial antivirus detected"),
    ).toBeInTheDocument();
  });

  test("shows an error when the initial fetch fails", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    render(<CommercialAntivirusStatusCard hostId="h1" />);
    expect(
      await screen.findByText("Failed to load commercial antivirus status"),
    ).toBeInTheDocument();
    expect(errSpy).toHaveBeenCalled();
  });

  test("does not fetch without a host id", () => {
    render(<CommercialAntivirusStatusCard hostId="" />);
    expect(mockGet).not.toHaveBeenCalled();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  test("auto-refreshes every 30 seconds and tolerates refresh errors", async () => {
    vi.useFakeTimers();
    render(<CommercialAntivirusStatusCard hostId="h1" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("Windows Defender")).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledTimes(1);

    mockGet.mockResolvedValueOnce({ ...FULL, product_name: "CrowdStrike Falcon" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(mockGet).toHaveBeenCalledTimes(2);
    expect(screen.getByText("CrowdStrike Falcon")).toBeInTheDocument();

    mockGet.mockRejectedValueOnce(new Error("down"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(mockGet).toHaveBeenCalledTimes(3);
    // A failed background refresh keeps the last good data on screen.
    expect(screen.getByText("CrowdStrike Falcon")).toBeInTheDocument();
    expect(errSpy).toHaveBeenCalledWith(
      "Error refreshing commercial antivirus status:",
      expect.any(Error),
    );
  });
});

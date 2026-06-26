import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
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
  doGetFederationSite: vi.fn(),
  doGetFederationSiteSyncStatus: vi.fn(),
  doGetFederationSiteSyncTimeline: vi.fn(),
  doListFederationCommands: vi.fn(),
  doGetFederationDashboardRollup: vi.fn(),
  doListFederationAlerts: vi.fn(),
  doAcknowledgeFederationAlert: vi.fn(),
  doSuspendFederationSite: vi.fn(),
  doResumeFederationSite: vi.fn(),
  doRemoveFederationSite: vi.fn(),
  doRepushSitePolicies: vi.fn(),
  doDispatchFederationCommand: vi.fn(),
}));

// Stub the dispatch dialog (covered by its own test) to keep this page
// test's MUI render — and the worker heap — light.
vi.mock("../../Components/FederationCommandDispatchDialog", () => ({
  default: () => null,
}));

import * as fed from "../../Services/federation";
import SiteDetail from "../../Pages/SiteDetail";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/sites/site-1"]}>
      <Routes>
        <Route path="/sites/:siteId" element={<SiteDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

function primeOk(site = { id: "site-1", name: "Alpha", status: "enrolled" }) {
  m(fed.doGetFederationSite).mockResolvedValue({ licensed: true, site });
  m(fed.doGetFederationSiteSyncStatus).mockResolvedValue({
    licensed: true,
    status: { last_sync_at: null, last_sync_status: null },
  });
  m(fed.doListFederationCommands).mockResolvedValue({
    licensed: true,
    commands: [],
  });
  m(fed.doGetFederationDashboardRollup).mockResolvedValue({
    licensed: true,
    compliance_rollups: [],
    vulnerability_rollup: null,
  });
  m(fed.doListFederationAlerts).mockResolvedValue({ licensed: true, alerts: [] });
  m(fed.doGetFederationSiteSyncTimeline).mockResolvedValue({
    licensed: true,
    site_id: "site-1",
    connection_state: "online",
    sysmanage_version: null,
    capabilities: [],
    events: [],
  });
}

beforeEach(() => vi.clearAllMocks());

test("shows the Enterprise upsell when unlicensed", async () => {
  m(fed.doGetFederationSite).mockResolvedValue({ licensed: false });
  m(fed.doGetFederationSiteSyncStatus).mockResolvedValue({ licensed: false });
  m(fed.doListFederationCommands).mockResolvedValue({ licensed: false });
  m(fed.doGetFederationDashboardRollup).mockResolvedValue({ licensed: false });
  m(fed.doListFederationAlerts).mockResolvedValue({ licensed: false });
  renderPage();
  expect(
    await screen.findByText(/Multi-site federation requires Enterprise/i),
  ).toBeTruthy();
});

test("renders the site name and connection-health card", async () => {
  primeOk();
  renderPage();
  expect(await screen.findByText("Alpha")).toBeTruthy();
  expect(screen.getByText(/Connection health/i)).toBeTruthy();
});

test("shows an open-alert card with an acknowledge action", async () => {
  primeOk();
  m(fed.doListFederationAlerts).mockResolvedValue({
    licensed: true,
    alerts: [
      {
        id: "al1",
        site_id: "site-1",
        condition: "site_offline",
        severity: "critical",
        title: "Site Alpha is offline",
        message: "no sync",
        resolved: false,
        acknowledged: false,
      },
    ],
  });
  renderPage();
  expect(await screen.findByText("Site Alpha is offline")).toBeTruthy();
  expect(screen.getByTestId("ack-alert")).toBeTruthy();
});

test("renders the sync-timeline card with an empty state by default", async () => {
  primeOk();
  renderPage();
  await screen.findByText("Alpha");
  expect(screen.getByTestId("sync-timeline-card")).toBeTruthy();
  expect(screen.getByText(/No sync events recorded yet/i)).toBeTruthy();
  // No autonomy banner while the site reports online.
  expect(screen.queryByTestId("autonomy-banner")).toBeNull();
});

test("plots a latency sparkline and reports version + capabilities", async () => {
  primeOk();
  m(fed.doGetFederationSiteSyncTimeline).mockResolvedValue({
    licensed: true,
    site_id: "site-1",
    connection_state: "online",
    sysmanage_version: "2.4.0.0",
    capabilities: ["federation_site_engine"],
    events: [
      { recorded_at: "t1", sync_status: "success", latency_ms: 30, queue_depth: 1, host_count: 5 },
      { recorded_at: "t2", sync_status: "success", latency_ms: 45, queue_depth: 0, host_count: 5 },
    ],
  });
  renderPage();
  expect(await screen.findByTestId("sync-latency-sparkline")).toBeTruthy();
  expect(screen.getByTestId("site-version").textContent).toContain("2.4.0.0");
  expect(screen.getByText("federation_site_engine")).toBeTruthy();
});

test("shows the autonomy banner when the site reports offline", async () => {
  primeOk();
  m(fed.doGetFederationSiteSyncTimeline).mockResolvedValue({
    licensed: true,
    site_id: "site-1",
    connection_state: "offline",
    sysmanage_version: "2.4.0.0",
    capabilities: [],
    events: [
      { recorded_at: "t1", sync_status: "error", latency_ms: null, queue_depth: 9, host_count: 5 },
    ],
  });
  renderPage();
  expect(await screen.findByTestId("autonomy-banner")).toBeTruthy();
});

test("exposes per-site action buttons; dispatch is enabled only when enrolled", async () => {
  primeOk();
  renderPage();
  await screen.findByText("Alpha");
  const dispatch = screen.getByTestId("header-dispatch-button");
  expect(dispatch).toBeTruthy();
  expect(dispatch.hasAttribute("disabled")).toBe(false);
  expect(screen.getByTestId("header-policies-button")).toBeTruthy();
});

test("disables the header dispatch action for a suspended site", async () => {
  primeOk({ id: "site-1", name: "Alpha", status: "suspended" });
  renderPage();
  await screen.findByText("Alpha");
  const dispatch = screen.getByTestId("header-dispatch-button");
  expect(dispatch.hasAttribute("disabled")).toBe(true);
});

test("Push policies re-queues the site's policies and confirms", async () => {
  const { fireEvent, waitFor } = await import("@testing-library/react");
  primeOk();
  m(fed.doRepushSitePolicies).mockResolvedValue({
    licensed: true,
    requeued_count: 3,
  });
  renderPage();
  await screen.findByText("Alpha");
  fireEvent.click(screen.getByTestId("header-policies-button"));
  await waitFor(() =>
    expect(m(fed.doRepushSitePolicies)).toHaveBeenCalledWith("site-1"),
  );
  expect(await screen.findByText(/Queued 3 policy push/i)).toBeTruthy();
});

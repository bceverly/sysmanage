// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The configuration drift dashboard.
 *
 * Two things must be unmistakable to whoever reads this page at 3am.
 *
 * **Nothing here has been changed.** Drift is found by DRY RUNS. If the page
 * read as a list of changes already made, an operator would go hunting for a
 * rollback that never happened.
 *
 * **Remediation is a real change, and it is confirmed by name.** The dialog
 * names both the host and the profile, because "are you sure?" without a
 * subject is not a check — it is a speed bump.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
  let s = typeof fallback === "string" ? fallback : key;
  if (opts) {
    for (const [k, v] of Object.entries(opts)) {
      s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
    }
  }
  return s;
};
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
  }: {
    rows?: any[];
    columns?: any[];
  }) => (
    <div data-testid="grid">
      {(rows ?? []).map((row) => (
        <div key={String(row.host_id)} data-testid="row">
          {(columns ?? []).map((col) => (
            <div key={col.field}>
              {col.renderCell
                ? col.renderCell({ row, value: row[col.field] })
                : String(row[col.field] ?? "")}
            </div>
          ))}
        </div>
      ))}
    </div>
  ),
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

vi.mock("../../Services/configManagementService", () => ({
  getConfigProfiles: vi.fn().mockResolvedValue([]),
  getDriftingHosts: vi.fn(),
  getHostDrift: vi.fn(),
  remediateDrift: vi.fn(),
  // Used by the embedded BaselineDiffPanel. Resolved rather than left
  // undefined so the panel settles instead of leaving a pending promise that
  // updates state after the test ends.
  getBaselineCategories: vi.fn().mockResolvedValue([]),
  getBaselineDiff: vi.fn(),
}));

// Remediation playbooks (Phase 20.1). Mocked even though the page tolerates a
// rejection here: an unmocked service would make real HTTP calls from jsdom,
// and a test whose result depends on a network timeout is not a test.
vi.mock("../../Services/configFleetService", () => ({
  getFindingRemediation: vi.fn().mockResolvedValue({
    finding_id: "f1",
    matched: false,
    unavailable: false,
    rule_id: null,
    rule_name: null,
    remediation_profile_id: null,
    remediation_profile_name: null,
    preview: null,
  }),
  repairFinding: vi.fn(),
  getRemediationRules: vi.fn().mockResolvedValue([]),
  createRemediationRule: vi.fn(),
  updateRemediationRule: vi.fn(),
  deleteRemediationRule: vi.fn(),
}));

// The panel loads its own candidate reference hosts.
vi.mock("../../Services/scripts", () => ({
  // NAMED export, matching the real module. Mocking a `default` here made the
  // suite pass while the app failed to mount at all ("does not provide an
  // export named 'default'") -- the mock invented an API the module has not
  // got.
  scriptsService: { getActiveHosts: vi.fn().mockResolvedValue([]) },
}));

import { hasPermission } from "../../Services/permissions";
import {
  getDriftingHosts,
  getHostDrift,
  remediateDrift,
} from "../../Services/configManagementService";
import {
  getFindingRemediation,
  repairFinding,
} from "../../Services/configFleetService";
import ConfigDrift from "../../Pages/ConfigDrift";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const daysAgo = (n: number) =>
  new Date(Date.now() - n * 86_400_000).toISOString();

const hostSummary = (over = {}) => ({
  host_id: "h1",
  host_fqdn: "web01.invalid",
  finding_count: 2,
  profile_names: ["baseline"],
  drifting_since: daysAgo(9),
  ...over,
});

const finding = (over = {}) => ({
  id: "f1",
  host_id: "h1",
  host_fqdn: "web01.invalid",
  profile_id: "p1",
  profile_name: "baseline",
  task_name: "ensure sshd config",
  detail: "would set mode 0600",
  first_seen_at: daysAgo(9),
  last_seen_at: daysAgo(0),
  resolved_at: null,
  last_run_id: "r1",
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  m(hasPermission).mockResolvedValue(true);
  m(getDriftingHosts).mockResolvedValue([hostSummary()]);
  m(getHostDrift).mockResolvedValue([finding()]);
  m(remediateDrift).mockResolvedValue({
    host_id: "h1",
    profile_id: "p1",
    queued: true,
    message: "Remediation was queued for this host",
  });
});

describe("the fleet view", () => {
  test("drifting hosts are listed", async () => {
    render(<ConfigDrift />);
    expect(await screen.findByText("web01.invalid")).toBeInTheDocument();
  });

  test("a clean fleet says so instead of showing an empty grid", async () => {
    // An empty table reads as "no data"; this is genuinely good news and
    // should look like it.
    m(getDriftingHosts).mockResolvedValue([]);
    render(<ConfigDrift />);
    expect(
      await screen.findByText(/Every host matches its assigned profile/),
    ).toBeInTheDocument();
  });

  test("drift age is shown in days, not a raw timestamp", async () => {
    // "9 days" is the triage signal; the exact moment it began rarely changes
    // what an operator does next.
    render(<ConfigDrift />);
    expect(await screen.findByText("9 days")).toBeInTheDocument();
  });

  test("a host with no fqdn still identifies itself", async () => {
    m(getDriftingHosts).mockResolvedValue([
      hostSummary({ host_fqdn: null }),
    ]);
    render(<ConfigDrift />);
    expect(await screen.findByText("h1")).toBeInTheDocument();
  });

  test("a load failure surfaces the server's reason", async () => {
    m(getDriftingHosts).mockRejectedValue({
      response: { data: { detail: "config_management_engine is not licensed" } },
    });
    render(<ConfigDrift />);
    expect(
      await screen.findByText("config_management_engine is not licensed"),
    ).toBeInTheDocument();
  });

  test("the page says drift was found by dry runs, not applied", async () => {
    // The single most important sentence on the page.
    render(<ConfigDrift />);
    await screen.findByText("web01.invalid");
    expect(
      screen.getByText(/nothing here has been changed/i),
    ).toBeInTheDocument();
  });
});

describe("host detail", () => {
  const openDetail = async () => {
    render(<ConfigDrift />);
    await screen.findByText("web01.invalid");
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    await waitFor(() => expect(m(getHostDrift)).toHaveBeenCalledWith("h1"));
  };

  test("the specific differences are shown", async () => {
    await openDetail();
    expect(await screen.findByText("ensure sshd config")).toBeInTheDocument();
    expect(screen.getByText("would set mode 0600")).toBeInTheDocument();
  });

  test("a finding with no detail still renders something useful", async () => {
    m(getHostDrift).mockResolvedValue([finding({ detail: null })]);
    await openDetail();
    expect(
      await screen.findByText(/No further detail reported/),
    ).toBeInTheDocument();
  });

  test("a findings failure is reported inside the dialog", async () => {
    m(getHostDrift).mockRejectedValue(new Error("host unreachable"));
    await openDetail();
    expect(
      await screen.findByText(/Could not load the findings/),
    ).toBeInTheDocument();
  });
});

describe("remediation", () => {
  const openDetail = async () => {
    render(<ConfigDrift />);
    await screen.findByText("web01.invalid");
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    await waitFor(() => expect(m(getHostDrift)).toHaveBeenCalled());
  };

  test("without RUN_SCRIPT no remediate control is offered", async () => {
    m(hasPermission).mockResolvedValue(false);
    await openDetail();
    await screen.findByText("ensure sshd config");
    expect(screen.queryByText("Remediate to baseline")).toBeNull();
  });

  test("clicking remediate asks first and never fires immediately", async () => {
    await openDetail();
    fireEvent.click(await screen.findByText("Remediate to baseline"));
    expect(m(remediateDrift)).not.toHaveBeenCalled();
  });

  test("the confirmation names both the host and the profile", async () => {
    // "Are you sure?" without a subject is a speed bump, not a check.
    await openDetail();
    fireEvent.click(await screen.findByText("Remediate to baseline"));
    const body = await screen.findByText(/runs baseline on web01.invalid/);
    expect(body).toBeInTheDocument();
  });

  test("the confirmation warns that a maintenance window may hold it", async () => {
    await openDetail();
    fireEvent.click(await screen.findByText("Remediate to baseline"));
    expect(
      await screen.findByText(/maintenance\s+window/i),
    ).toBeInTheDocument();
  });

  test("confirming queues the remediation for that host and profile", async () => {
    await openDetail();
    fireEvent.click(await screen.findByText("Remediate to baseline"));
    fireEvent.click(await screen.findByRole("button", { name: "Remediate" }));
    await waitFor(() =>
      expect(m(remediateDrift)).toHaveBeenCalledWith("h1", "p1"),
    );
  });

  test("the drift list is NOT refreshed after queuing", async () => {
    // The findings stay open until a check run confirms the fix. Refreshing
    // would redisplay identical drift and read as "the button did nothing".
    await openDetail();
    const before = m(getDriftingHosts).mock.calls.length;
    fireEvent.click(await screen.findByText("Remediate to baseline"));
    fireEvent.click(await screen.findByRole("button", { name: "Remediate" }));
    await waitFor(() => expect(m(remediateDrift)).toHaveBeenCalled());
    expect(m(getDriftingHosts).mock.calls.length).toBe(before);
  });

  test("a refused remediation is reported", async () => {
    m(remediateDrift).mockRejectedValue({
      response: { data: { detail: "This profile is not active" } },
    });
    await openDetail();
    fireEvent.click(await screen.findByText("Remediate to baseline"));
    fireEvent.click(await screen.findByRole("button", { name: "Remediate" }));
    expect(
      await screen.findByText("This profile is not active"),
    ).toBeInTheDocument();
  });

  test("cancelling sends nothing", async () => {
    await openDetail();
    fireEvent.click(await screen.findByText("Remediate to baseline"));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(m(remediateDrift)).not.toHaveBeenCalled());
  });
});

describe("ConfigDrift — remediation playbooks", () => {
  const openDetail = async () => {
    render(<ConfigDrift />);
    await screen.findByText("web01.invalid");
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    await waitFor(() => expect(m(getHostDrift)).toHaveBeenCalledWith("h1"));
  };

  const matched = (over = {}) => ({
    finding_id: "f1",
    matched: true,
    unavailable: false,
    rule_id: "r1",
    rule_name: "sshd repair",
    remediation_profile_id: "p2",
    remediation_profile_name: "sshd fix",
    preview: { rule_name: "sshd repair" },
    ...over,
  });

  test("a finding with no matching rule offers only the baseline re-apply", async () => {
    // The behaviour before playbooks existed, and the right fallback: a rule
    // library nobody has written yet must not remove the repair that works.
    await openDetail();
    expect(await screen.findByText("Remediate to baseline")).toBeInTheDocument();
    expect(screen.queryByText(/Repair with/)).not.toBeInTheDocument();
  });

  test("a matched playbook is offered by name", async () => {
    m(getFindingRemediation).mockResolvedValue(matched());
    await openDetail();
    expect(await screen.findByText("Repair with sshd fix")).toBeInTheDocument();
  });

  test("the targeted repair is offered ahead of the baseline re-apply", async () => {
    // Re-applying a four-hundred-task baseline to fix one file mode is the
    // blunter of the two, and button order is what says so.
    m(getFindingRemediation).mockResolvedValue(matched());
    await openDetail();
    const targeted = await screen.findByText("Repair with sshd fix");
    const baseline = screen.getByText("Remediate to baseline");
    // DOCUMENT_POSITION_FOLLOWING (4) read off the element rather than the
    // global `Node`, which the test lint config does not expose.
    const FOLLOWING = 4;
    expect(targeted.compareDocumentPosition(baseline) & FOLLOWING).toBeTruthy();
  });

  test("a rule whose repair profile was retired says so instead of offering it", async () => {
    // Two different problems: "nothing knows how to fix this" sends you to
    // write a rule, "the fix was turned off" sends you to turn it back on.
    m(getFindingRemediation).mockResolvedValue(
      matched({ unavailable: true, remediation_profile_name: null }),
    );
    await openDetail();
    expect(
      await screen.findByText("Its repair profile is not active"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Repair with/)).not.toBeInTheDocument();
  });

  test("the targeted repair fires without a second confirmation dialog", async () => {
    // Unlike the baseline button, this one already names its subject on the
    // face of it: "Repair with sshd fix" IS the confirmation.
    m(getFindingRemediation).mockResolvedValue(matched());
    m(repairFinding).mockResolvedValue({
      finding_id: "f1",
      host_id: "h1",
      profile_id: "p2",
      profile_name: "sshd fix",
      queued: true,
      message: "The repair was queued for this host",
    });
    await openDetail();
    fireEvent.click(await screen.findByText("Repair with sshd fix"));
    await waitFor(() => expect(m(repairFinding)).toHaveBeenCalledWith("f1"));
    expect(
      await screen.findByText("The repair was queued for this host"),
    ).toBeInTheDocument();
  });

  test("a refused repair is reported with the server's reason", async () => {
    m(getFindingRemediation).mockResolvedValue(matched());
    m(repairFinding).mockRejectedValue({
      response: { data: { detail: "Host is not active" } },
    });
    await openDetail();
    fireEvent.click(await screen.findByText("Repair with sshd fix"));
    expect(await screen.findByText("Host is not active")).toBeInTheDocument();
  });

  test("one failed lookup does not hide every other finding's repair", async () => {
    // Promise.allSettled, not all: a single lookup error must not take the
    // whole dialog's remediation options with it.
    m(getFindingRemediation).mockRejectedValue(new Error("boom"));
    await openDetail();
    expect(await screen.findByText("Remediate to baseline")).toBeInTheDocument();
  });

  test("the playbooks tab is reachable from this page", async () => {
    // A rule is written in response to drift you are looking at, so the two
    // belong one click apart rather than in separate nav entries.
    render(<ConfigDrift />);
    expect(
      await screen.findByText("Remediation playbooks"),
    ).toBeInTheDocument();
  });
});

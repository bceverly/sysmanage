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
  getDriftingHosts: vi.fn(),
  getHostDrift: vi.fn(),
  remediateDrift: vi.fn(),
}));

import { hasPermission } from "../../Services/permissions";
import {
  getDriftingHosts,
  getHostDrift,
  remediateDrift,
} from "../../Services/configManagementService";
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

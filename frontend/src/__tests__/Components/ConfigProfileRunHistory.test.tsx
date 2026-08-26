// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Config-profile run history (Phase 20.1).
 *
 * The property under test is that a SUCCESSFUL run and an UNCHANGED run are
 * shown differently. Collapsing them into one green tick would destroy the
 * only thing this panel exists for: seeing that a converged profile has
 * stopped changing anything. A dry run must likewise never be mistaken for an
 * applied change.
 */

import { render, screen } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module -- the fetch callback lists `t` in its deps, so a fresh
// identity each render loops forever.
vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallback?: string,
    opts?: Record<string, unknown>,
  ) => {
    let out = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        out = out.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return out;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/configManagementService", () => ({
  getConfigProfileRuns: vi.fn(),
}));

import { getConfigProfileRuns } from "../../Services/configManagementService";
import ConfigProfileRunHistory from "../../Components/ConfigProfileRunHistory";

const run = (over = {}) => ({
  id: "r1",
  host_id: "h1",
  profile_id: null,
  profile_name: "baseline",
  executor: "ansible-core",
  check_mode: false,
  success: true,
  changed: false,
  exit_code: 0,
  tasks_ok: 3,
  tasks_changed: 0,
  tasks_failed: 0,
  tasks_skipped: 1,
  tasks_unreachable: 0,
  reason: null,
  completed_at: "2026-08-26T12:00:00Z",
  ...over,
});

describe("ConfigProfileRunHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window.console, "error").mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  test("an unchanged run reads as No changes, not just success", async () => {
    vi.mocked(getConfigProfileRuns).mockResolvedValue([run()]);
    render(<ConfigProfileRunHistory hostId="h1" />);
    expect(await screen.findByText("No changes")).toBeInTheDocument();
    expect(screen.queryByText("Changed")).not.toBeInTheDocument();
  });

  test("a changed run is visually distinct from an unchanged one", async () => {
    vi.mocked(getConfigProfileRuns).mockResolvedValue([
      run({ id: "r2", changed: true, tasks_changed: 2 }),
    ]);
    render(<ConfigProfileRunHistory hostId="h1" />);
    expect(await screen.findByText("Changed")).toBeInTheDocument();
    expect(screen.queryByText("No changes")).not.toBeInTheDocument();
  });

  test("a failed run outranks the changed/unchanged distinction", async () => {
    vi.mocked(getConfigProfileRuns).mockResolvedValue([
      run({ success: false, changed: true }),
    ]);
    render(<ConfigProfileRunHistory hostId="h1" />);
    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.queryByText("Changed")).not.toBeInTheDocument();
  });

  test("a dry run is labelled so it cannot be read as applied", async () => {
    vi.mocked(getConfigProfileRuns).mockResolvedValue([
      run({ check_mode: true }),
    ]);
    render(<ConfigProfileRunHistory hostId="h1" />);
    expect(await screen.findByText("Dry run")).toBeInTheDocument();
  });

  test("the quiet streak is visible -- every no-op run is listed", async () => {
    vi.mocked(getConfigProfileRuns).mockResolvedValue([
      run({ id: "a" }),
      run({ id: "b" }),
      run({ id: "c" }),
    ]);
    render(<ConfigProfileRunHistory hostId="h1" />);
    expect(await screen.findAllByText("No changes")).toHaveLength(3);
  });

  test("task counts are rendered from the recap", async () => {
    vi.mocked(getConfigProfileRuns).mockResolvedValue([
      run({ tasks_ok: 5, tasks_changed: 2, tasks_failed: 1 }),
    ]);
    render(<ConfigProfileRunHistory hostId="h1" />);
    expect(
      await screen.findByText("5 ok, 2 changed, 1 failed"),
    ).toBeInTheDocument();
  });

  test("a run with no profile name says so", async () => {
    vi.mocked(getConfigProfileRuns).mockResolvedValue([
      run({ profile_name: null }),
    ]);
    render(<ConfigProfileRunHistory hostId="h1" />);
    expect(await screen.findByText("No profile")).toBeInTheDocument();
  });

  test("a host with no runs says so rather than showing an empty table", async () => {
    vi.mocked(getConfigProfileRuns).mockResolvedValue([]);
    render(<ConfigProfileRunHistory hostId="h1" />);
    expect(
      await screen.findByText(
        "No configuration profiles have been applied to this host yet.",
      ),
    ).toBeInTheDocument();
  });

  test("a failed fetch surfaces an error rather than an empty panel", async () => {
    vi.mocked(getConfigProfileRuns).mockRejectedValue(new Error("boom"));
    render(<ConfigProfileRunHistory hostId="h1" />);
    expect(
      await screen.findByText("Failed to load configuration run history"),
    ).toBeInTheDocument();
  });
});

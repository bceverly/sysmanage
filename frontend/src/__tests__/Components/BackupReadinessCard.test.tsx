// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Restore readiness (27.1, Enterprise): shown only with the engine, worst
// hosts first, every host on request, and the RPO editable.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const fill = (text: string, opts?: Record<string, unknown>) =>
    text.replace(/\{\{(\w+)\}\}/g, (_m, key) => String(opts?.[key] ?? ""));
  const value = {
    t: (k: string, f?: string | Record<string, unknown>, o?: Record<string, unknown>) =>
      typeof f === "string" ? fill(f, o) : k,
    i18n: { language: "en" },
  };
  return { useTranslation: () => value };
});
vi.mock("../../hooks/useModuleLicensed", () => ({ useModuleLicensed: vi.fn(() => true) }));
vi.mock("../../Services/backupReadiness", async (orig) => ({
  ...(await orig<typeof import("../../Services/backupReadiness")>()),
  getReadiness: vi.fn(),
  setRpo: vi.fn(),
}));

import { useModuleLicensed } from "../../hooks/useModuleLicensed";
import { getReadiness, setRpo } from "../../Services/backupReadiness";
import type { FleetReadiness } from "../../Services/backupReadiness";
import BackupReadinessCard, { formatDuration } from "../../Components/Backups/BackupReadinessCard";

const t = ((k: string, f: string, o?: Record<string, unknown>) =>
  f.replace(/\{\{(\w+)\}\}/g, (_m, key) => String(o?.[key] ?? ""))) as never;

const DATA: FleetReadiness = {
  counts: { never_backed_up: 0, rpo_breached: 0, unproven: 1, ready: 1 },
  hosts: [
    { host_id: "h1", fqdn: "web.lan", policy_id: "p1", enabled: true, state: "unproven",
      reasons: ["never_proven"], rpo: { target_hours: 48, age_hours: 10, met: true },
      rto: { seconds: 500, basis: "capture", mb_per_s: 100 }, proof: null },
    { host_id: "h2", fqdn: "db.lan", policy_id: "p2", enabled: true, state: "ready",
      reasons: [], rpo: { target_hours: 48, age_hours: 5, met: true },
      rto: { seconds: 7200, basis: "verify", mb_per_s: 50 },
      proof: { kind: "verify", at: "2026-11-18T00:00:00", fresh: true } },
  ],
};

beforeEach(() => {
  vi.mocked(useModuleLicensed).mockReturnValue(true);
  vi.mocked(getReadiness).mockResolvedValue(DATA);
  vi.mocked(setRpo).mockReset();
});

test("nothing without the engine", () => {
  vi.mocked(useModuleLicensed).mockReturnValue(false);
  const { container } = render(<BackupReadinessCard canManage />);
  expect(container).toBeEmptyDOMElement();
  expect(getReadiness).not.toHaveBeenCalled();
});

test("hosts needing a look first, every host on request", async () => {
  render(<BackupReadinessCard canManage />);
  expect(await screen.findByText("web.lan")).toBeInTheDocument();
  expect(screen.getByText("Unproven: 1")).toBeInTheDocument();
  expect(screen.getByText("never proven")).toBeInTheDocument();
  expect(screen.getByText("10 h ago / 48 h")).toBeInTheDocument();
  expect(screen.queryByText("db.lan")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Show every host"));
  expect(screen.getByText("db.lan")).toBeInTheDocument();
});

test("the recovery point objective can be changed", async () => {
  vi.mocked(setRpo).mockResolvedValue({});
  render(<BackupReadinessCard canManage />);
  fireEvent.click(await screen.findByRole("button", { name: "Change the recovery point objective" }));
  fireEvent.change(screen.getByLabelText("Hours"), { target: { value: "12" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(setRpo).toHaveBeenCalledWith("h1", 12));
});

test("restore times read as estimates", () => {
  expect(formatDuration(t, null)).toBe("unknown");
  expect(formatDuration(t, 60)).toBe("about a minute");
  expect(formatDuration(t, 500)).toBe("about 8 min");
  expect(formatDuration(t, 9000)).toBe("about 2.5 h");
});

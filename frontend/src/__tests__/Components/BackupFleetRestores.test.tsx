// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Fleet restores (27.2, Enterprise): the jobs with each host's outcome, a new
// job's form, Cancel; hidden without the engine or the restore role.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
vi.mock("../../Services/backupFleetRestore", () => ({
  listFleetRestores: vi.fn(), getFleetRestore: vi.fn(),
  createFleetRestore: vi.fn(), cancelFleetRestore: vi.fn(),
}));

import { useModuleLicensed } from "../../hooks/useModuleLicensed";
import {
  cancelFleetRestore, createFleetRestore, getFleetRestore, listFleetRestores,
} from "../../Services/backupFleetRestore";
import BackupFleetRestoresCard from "../../Components/Backups/BackupFleetRestores";

const HOSTS = [{ host_id: "h1", fqdn: "web01.lan" }, { host_id: "h2", fqdn: "web02.lan" }];
const job = (over: Record<string, unknown> = {}) => ({
  id: "j1", name: "after the incident", status: "running", include: ["/etc/nginx"],
  exclude: [], before: null, in_place: false, dry_run: false, concurrency: 5,
  created_by: "alice@example.com", created_at: "2026-11-24T10:00:00", approved_by: null,
  finished_at: null, hosts: 2, counts: { ok: 1, running: 1 }, ...over,
});

beforeEach(() => {
  vi.mocked(useModuleLicensed).mockReturnValue(true);
  vi.mocked(listFleetRestores).mockResolvedValue([job()]);
  vi.mocked(createFleetRestore).mockResolvedValue(job());
  vi.mocked(cancelFleetRestore).mockResolvedValue(job({ status: "canceled" }));
  vi.mocked(getFleetRestore).mockResolvedValue(job({
    targets: [
      { host_id: "h1", fqdn: "web01.lan", status: "ok", snapshot: "S1", run_id: "r1",
        message: null, started_at: null, finished_at: null },
      { host_id: "h2", fqdn: "web02.lan", status: "skipped", snapshot: null, run_id: null,
        message: "No snapshot to restore from", started_at: null, finished_at: null },
    ],
  }));
});

test("lists the jobs with each state's count, and each host's outcome", async () => {
  render(<BackupFleetRestoresCard canRestore hosts={HOSTS} />);
  expect(await screen.findByText("after the incident")).toBeTruthy();
  expect(screen.getByText("Restored: 1")).toBeTruthy();
  expect(screen.getByText("Restoring: 1")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Hosts" }));
  expect(await screen.findByText("No snapshot to restore from")).toBeTruthy();
  expect(screen.getByText("Skipped")).toBeTruthy();
});

test("cancel is offered while it runs", async () => {
  render(<BackupFleetRestoresCard canRestore hosts={HOSTS} />);
  fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(cancelFleetRestore).toHaveBeenCalledWith("j1"));
});

test("an in-place restore cannot start until the replacement is confirmed", async () => {
  render(<BackupFleetRestoresCard canRestore hosts={HOSTS} />);
  fireEvent.click(await screen.findByRole("button", { name: "New fleet restore" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "nginx back" } });
  fireEvent.change(within(dialog).getByLabelText("Paths to restore, one per line"), { target: { value: "/etc/nginx\n" } });
  const hosts = within(dialog).getByLabelText("Hosts");
  fireEvent.change(hosts, { target: { value: "web01" } });
  fireEvent.click(await screen.findByText("web01.lan"));
  const start = within(dialog).getByRole("button", { name: "Start the fleet restore" }) as HTMLButtonElement;
  expect(start.disabled).toBe(false);

  fireEvent.mouseDown(within(dialog).getByLabelText("Restore to"));
  fireEvent.click(await screen.findByText("Over each host's own files"));
  expect(start.disabled).toBe(true);
  fireEvent.click(within(dialog).getByLabelText("I understand each host's files at these paths will be replaced"));
  expect(start.disabled).toBe(false);
  fireEvent.click(start);
  await waitFor(() => expect(createFleetRestore).toHaveBeenCalled());
  const body = vi.mocked(createFleetRestore).mock.calls[0][0];
  expect(body).toMatchObject({
    name: "nginx back", host_ids: ["h1"], include: ["/etc/nginx"], in_place: true,
    acknowledge_in_place: true, dry_run: false, concurrency: 5, before: null,
  });
});

test("hidden without the engine or the restore role", async () => {
  vi.mocked(useModuleLicensed).mockReturnValue(false);
  const { container, rerender } = render(<BackupFleetRestoresCard canRestore hosts={HOSTS} />);
  expect(container.innerHTML).toBe("");
  vi.mocked(useModuleLicensed).mockReturnValue(true);
  rerender(<BackupFleetRestoresCard canRestore={false} hosts={HOSTS} />);
  expect(container.innerHTML).toBe("");
});

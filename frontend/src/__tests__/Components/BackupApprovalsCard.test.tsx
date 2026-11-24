// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Four-eyes restore approval (27.2, Enterprise): the requester withdraws,
// someone else with the restore role approves or rejects.

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
vi.mock("../../Services/backupFourEyes", () => ({
  getFourEyes: vi.fn(), setFourEyes: vi.fn(), approveRestore: vi.fn(),
  rejectRestore: vi.fn(), withdrawRestore: vi.fn(),
}));

import { useModuleLicensed } from "../../hooks/useModuleLicensed";
import {
  approveRestore, getFourEyes, setFourEyes, withdrawRestore,
} from "../../Services/backupFourEyes";
import BackupApprovalsCard from "../../Components/Backups/BackupApprovalsCard";

const request = (over: Record<string, unknown>) => ({
  id: "r1", host_id: "h1", fqdn: "web.lan", status: "pending", snapshot: "S1",
  include: ["/etc/nginx"], packages: false, requested_by: "alice@example.com",
  requested_at: "2026-11-19T10:00:00", decided_by: null, decided_at: null,
  reason: null, run_id: null, ...over,
});

beforeEach(() => {
  vi.mocked(useModuleLicensed).mockReturnValue(true);
  vi.mocked(getFourEyes).mockResolvedValue({ enabled: true, ttl_hours: 24, requests: [request({})] });
  vi.mocked(approveRestore).mockResolvedValue({});
  vi.mocked(withdrawRestore).mockResolvedValue({});
  vi.mocked(setFourEyes).mockResolvedValue({ enabled: false });
  localStorage.setItem("userid", "bob@example.com");
});

test("nothing without the engine", () => {
  vi.mocked(useModuleLicensed).mockReturnValue(false);
  const { container } = render(<BackupApprovalsCard canManage canRestore />);
  expect(container).toBeEmptyDOMElement();
});

test("someone else with the restore role can approve", async () => {
  render(<BackupApprovalsCard canManage canRestore />);
  fireEvent.click(await screen.findByRole("button", { name: "Approve and restore" }));
  await waitFor(() => expect(approveRestore).toHaveBeenCalledWith("r1"));
  expect(screen.queryByRole("button", { name: "Withdraw" })).not.toBeInTheDocument();
});

test("the requester can only withdraw", async () => {
  localStorage.setItem("userid", "alice@example.com");
  render(<BackupApprovalsCard canManage canRestore />);
  fireEvent.click(await screen.findByRole("button", { name: "Withdraw" }));
  await waitFor(() => expect(withdrawRestore).toHaveBeenCalledWith("r1"));
  expect(screen.queryByRole("button", { name: "Approve and restore" })).not.toBeInTheDocument();
});

test("without the restore role nothing can be decided", async () => {
  render(<BackupApprovalsCard canManage canRestore={false} />);
  expect(await screen.findByText("web.lan")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Approve and restore" })).not.toBeInTheDocument();
});

test("the setting is switched by a backup manager", async () => {
  render(<BackupApprovalsCard canManage canRestore />);
  fireEvent.click(await screen.findByRole("switch"));
  await waitFor(() => expect(setFourEyes).toHaveBeenCalledWith(false));
});

test("a held fleet restore names its job and how many hosts (2026-11-24)", async () => {
  vi.mocked(getFourEyes).mockResolvedValue({
    enabled: true, ttl_hours: 24,
    requests: [request({ kind: "fleet_restore", name: "after the incident", hosts: 7, snapshot: null, include: [] })],
  });
  render(<BackupApprovalsCard canManage canRestore />);
  expect(await screen.findByText("Fleet restore")).toBeTruthy();
  expect(screen.getByText(/"after the incident" over the files of 7 hosts/)).toBeTruthy();
});

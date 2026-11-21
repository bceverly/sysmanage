// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Moving a host with its backups (27.3): the host's card says how far the
// copy has got, offers Cancel until the switch, says why a move stopped,
// and how long the old repository is kept after it.

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
vi.mock("../../Services/backups", () => ({ cancelMove: vi.fn() }));

import { cancelMove } from "../../Services/backups";
import { HostMove } from "../../Components/Backups/BackupMove";
import type { BackupMove } from "../../Services/backups";

const move = (extra: Partial<BackupMove> = {}): BackupMove => ({
  id: "m1", status: "copying", target: "Offsite", from_target: "NAS",
  total: 5, behind: 2, bytes: null, error: null, switched_at: null, keep_until: null,
  ...extra,
});

beforeEach(() => {
  vi.mocked(cancelMove).mockReset();
});

test("nothing without a move", () => {
  const { container } = render(<HostMove move={null} canManage onChanged={() => undefined} />);
  expect(container.textContent).toBe("");
});

test("a move under way shows its progress and can be canceled", async () => {
  const changed = vi.fn();
  vi.mocked(cancelMove).mockResolvedValueOnce(undefined);
  render(<HostMove move={move()} canManage onChanged={changed} />);
  expect(screen.getByTestId("host-move").textContent).toContain(
    "Moving to Offsite: snapshots copied 3 of 5");
  fireEvent.click(screen.getByText("Cancel move"));
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(cancelMove).toHaveBeenCalledWith("m1");
});

test("only a manager can cancel, and the check is named", () => {
  render(<HostMove move={move({ status: "verifying" })} canManage={false} onChanged={() => undefined} />);
  expect(screen.getByTestId("host-move").textContent).toContain("checking the copy");
  expect(screen.queryByText("Cancel move")).toBeNull();
});

test("a stopped move says the host stays where it is", () => {
  render(<HostMove move={move({ status: "failed", error: "check failed" })} canManage onChanged={() => undefined} />);
  expect(screen.getByTestId("host-move").textContent).toContain(
    "The move to Offsite stopped: check failed. This host still backs up to NAS.");
});

test("after the switch it says how long the old repository is kept", () => {
  const { rerender } = render(
    <HostMove move={move({ status: "switched", keep_until: "2026-12-04T03:00:00" })} canManage onChanged={() => undefined} />,
  );
  expect(screen.getByTestId("host-move").textContent).toContain("Moved from NAS; its old repository there is kept until");
  rerender(<HostMove move={move({ status: "switched" })} canManage onChanged={() => undefined} />);
  expect(screen.getByTestId("host-move").textContent).toBe("Moved from NAS; its old repository there is kept.");
});

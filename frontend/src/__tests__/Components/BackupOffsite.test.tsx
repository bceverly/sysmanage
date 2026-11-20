// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Off-site copies (27.3): the target card names where it copies to and who
// copies into it, and offers a change only where licensed; a host's card
// shows how far behind its copy is.

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
vi.mock("../../Services/backups", () => ({ setReplicaTarget: vi.fn() }));

import { setReplicaTarget } from "../../Services/backups";
import { HostOffsite, TargetOffsite } from "../../Components/Backups/BackupOffsite";
import type { BackupTarget, OffsiteCopy } from "../../Services/backups";

const target = (id: string, name: string, extra: Partial<BackupTarget> = {}) =>
  ({ id, name, storage_host_id: `nas-${id}`, ...extra }) as BackupTarget;

beforeEach(() => {
  vi.mocked(setReplicaTarget).mockReset();
});

test("the card names the off-site copy and who copies in", () => {
  const nas = target("a", "NAS", { replica_target: "Offsite", replica_target_id: "b" });
  const off = target("b", "Offsite", { copies_from: ["NAS"] });
  const { rerender } = render(
    <TargetOffsite target={nas} targets={[nas, off]} canChange={false} onChanged={() => undefined} />,
  );
  expect(screen.getByTestId("offsite-a").textContent).toContain("Off-site copy: Offsite");
  expect(screen.queryByText("Change")).toBeNull();
  rerender(<TargetOffsite target={off} targets={[nas, off]} canChange={false} onChanged={() => undefined} />);
  expect(screen.getByText("Holds the off-site copies of: NAS")).toBeInTheDocument();
});

test("a single target shows nothing", () => {
  const nas = target("a", "NAS");
  const { container } = render(
    <TargetOffsite target={nas} targets={[nas]} canChange onChanged={() => undefined} />,
  );
  expect(container.textContent).toBe("");
});

test("changing it sends the chosen target, and a refusal is shown", async () => {
  const nas = target("a", "NAS");
  const off = target("b", "Offsite", { location: "DC2" });
  const changed = vi.fn();
  vi.mocked(setReplicaTarget).mockRejectedValueOnce({
    response: { data: { detail: "The off-site copy must be on another storage host" } },
  });
  render(<TargetOffsite target={nas} targets={[nas, off]} canChange onChanged={changed} />);
  fireEvent.click(screen.getByText("Change"));
  fireEvent.change(screen.getByTestId("offsite-choice"), { target: { value: "b" } });
  fireEvent.click(screen.getByText("Save"));
  await waitFor(() =>
    expect(screen.getByText("The off-site copy must be on another storage host")).toBeInTheDocument(),
  );
  expect(setReplicaTarget).toHaveBeenCalledWith("a", "b");
  vi.mocked(setReplicaTarget).mockResolvedValueOnce(nas);
  fireEvent.click(screen.getByText("Save"));
  await waitFor(() => expect(changed).toHaveBeenCalled());
});

const copy = (extra: Partial<OffsiteCopy> = {}): OffsiteCopy => ({
  id: "r1", target_id: "b", target: "Offsite", newest_snapshot: "20261120T010000Z",
  lag_hours: 6, behind: 2, bytes: 1024, ready: true, last_copy_at: null,
  last_copy_status: "ok", last_copy_error: null, ...extra,
});

test("a host's copy says how old and how far behind", () => {
  render(<HostOffsite offsite={[copy()]} />);
  const line = screen.getByTestId("host-offsite-r1").textContent ?? "";
  expect(line).toContain("Off-site copy at Offsite");
  expect(line).toContain("newest snapshot 6 h old");
  expect(line).toContain("2 to copy");
});

test("a failed copy is a warning, and a new copy is being set up", () => {
  const { rerender } = render(
    <HostOffsite offsite={[copy({ last_copy_status: "failed", last_copy_error: "401" })]} />,
  );
  expect(screen.getByText("The last off-site copy did not finish: 401")).toBeInTheDocument();
  rerender(<HostOffsite offsite={[copy({ ready: false })]} />);
  expect(screen.getByTestId("host-offsite-r1").textContent).toContain("being set up");
});

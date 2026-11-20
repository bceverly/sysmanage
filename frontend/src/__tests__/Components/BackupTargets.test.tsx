// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Multiple backup targets (27.3, Enterprise): a card per target, the default
// named, and a picker that offers another target only where licensed.

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
vi.mock("../../Services/backups", () => ({ listTargets: vi.fn() }));
vi.mock("../../Components/Backups/BackupTargetCard", () => ({
  default: (props: { target: { name: string } | null; several?: boolean; canMakeDefault?: boolean }) => (
    <div data-testid="target-card">
      {props.target ? props.target.name : "none"}|{String(!!props.several)}|{String(!!props.canMakeDefault)}
    </div>
  ),
  TargetDialog: (props: { open: boolean }) => (props.open ? <div>new target dialog</div> : null),
}));

import { useModuleLicensed } from "../../hooks/useModuleLicensed";
import { listTargets } from "../../Services/backups";
import BackupTargets, { storageHostIds } from "../../Components/Backups/BackupTargets";
import TargetPicker from "../../Components/Backups/TargetPicker";
import type { BackupOverview, BackupTarget } from "../../Services/backups";

const target = (id: string, name: string, extra: Partial<BackupTarget> = {}) =>
  ({ id, name, storage_host_id: `nas-${id}`, is_default: false, ...extra }) as BackupTarget;

const overview = (targets: BackupTarget[]): BackupOverview =>
  ({ target: targets[0] ?? null, targets, hosts: [], counts: {}, restate_versions: [] }) as BackupOverview;

const BRIEF = [
  { id: "a", name: "NAS", location: "Office", is_default: true, hosts: 3, tag_policies: 0 },
  { id: "b", name: "Offsite", location: null, is_default: false, hosts: 1, tag_policies: 0 },
];

beforeEach(() => {
  vi.mocked(useModuleLicensed).mockReturnValue(true);
  vi.mocked(listTargets).mockResolvedValue(BRIEF);
});

test("one card per target, and another can be added where licensed", () => {
  render(<BackupTargets data={overview([target("a", "NAS"), target("b", "Offsite")])}
    canManage onChanged={() => undefined} />);
  const cards = screen.getAllByTestId("target-card").map(card => card.textContent);
  expect(cards).toEqual(["NAS|true|true", "Offsite|true|true"]);
  fireEvent.click(screen.getByTestId("add-backup-target"));
  expect(screen.getByText("new target dialog")).toBeInTheDocument();
});

test("without the engine there is no adding and no changing the default", () => {
  vi.mocked(useModuleLicensed).mockReturnValue(false);
  render(<BackupTargets data={overview([target("a", "NAS")])} canManage onChanged={() => undefined} />);
  expect(screen.getByTestId("target-card").textContent).toBe("NAS|false|false");
  expect(screen.queryByTestId("add-backup-target")).toBeNull();
});

test("before any target there is the set-up card", () => {
  render(<BackupTargets data={overview([])} canManage onChanged={() => undefined} />);
  expect(screen.getByTestId("target-card").textContent).toBe("none|false|false");
});

test("every storage host is known", () => {
  expect(storageHostIds(overview([target("a", "NAS"), target("b", "Offsite")]))).toEqual(["nas-a", "nas-b"]);
});

test("the picker hides with one target", async () => {
  vi.mocked(listTargets).mockResolvedValue([BRIEF[0]]);
  const { container } = render(<TargetPicker value="" onChange={() => undefined} />);
  await waitFor(() => expect(listTargets).toHaveBeenCalled());
  await act(async () => { await Promise.resolve(); });
  expect(container).toBeEmptyDOMElement();
});

test("without the engine only the default and the current target can be picked", async () => {
  vi.mocked(useModuleLicensed).mockReturnValue(false);
  render(<TargetPicker value="" onChange={() => undefined} followDefault />);
  fireEvent.mouseDown(await screen.findByRole("combobox"));
  const list = within(screen.getByRole("listbox"));
  expect(list.getByText("The default (NAS)")).toBeInTheDocument();
  expect(list.getByText("NAS (Office)").closest("li")).not.toHaveAttribute("aria-disabled", "true");
  expect(list.getByText("Offsite").closest("li")).toHaveAttribute("aria-disabled", "true");
});

test("a host's own policy picks a target, never 'the default'", async () => {
  const chosen = vi.fn();
  render(<TargetPicker value="" onChange={chosen} />);
  fireEvent.mouseDown(await screen.findByRole("combobox"));
  const list = within(screen.getByRole("listbox"));
  expect(list.queryByText("The default (NAS)")).toBeNull();
  fireEvent.click(list.getByText("Offsite"));
  expect(chosen).toHaveBeenCalledWith("b");
});

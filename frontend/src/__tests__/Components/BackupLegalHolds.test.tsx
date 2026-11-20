// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Legal hold (27.2, Enterprise): placed with whose and why, released from
// the Backups page.

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
vi.mock("../../Services/backupLegalHold", () => ({
  getLegalHolds: vi.fn(), placeLegalHold: vi.fn(), releaseLegalHold: vi.fn(),
}));
vi.mock("../../Services/backups", () => ({ getSnapshots: vi.fn() }));

import { useModuleLicensed } from "../../hooks/useModuleLicensed";
import { getLegalHolds, placeLegalHold, releaseLegalHold } from "../../Services/backupLegalHold";
import { getSnapshots } from "../../Services/backups";
import BackupLegalHoldsCard, { LegalHoldButton } from "../../Components/Backups/BackupLegalHolds";

const HOLD = {
  id: "k1", host_id: "h1", fqdn: "web.lan", snapshot: "20261101T010000Z",
  owner: "Case 114", reason: "Litigation", placed_by: "alice@example.com",
  placed_at: "2026-11-19T10:00:00", released_by: null, released_at: null,
};

beforeEach(() => {
  vi.mocked(useModuleLicensed).mockReturnValue(true);
  vi.mocked(getLegalHolds).mockResolvedValue([HOLD]);
  vi.mocked(releaseLegalHold).mockResolvedValue(HOLD);
  vi.mocked(placeLegalHold).mockResolvedValue(HOLD);
  vi.mocked(getSnapshots).mockResolvedValue([
    { id: "s1", name: "20261101T010000Z", created_at: "2026-11-01T01:00:00",
      bytes: 1, new_bytes: 1, unique_bytes: 1, files: 1, signed: true },
  ] as never);
});

test("nothing without the engine", () => {
  vi.mocked(useModuleLicensed).mockReturnValue(false);
  const { container } = render(<BackupLegalHoldsCard canManage />);
  expect(container).toBeEmptyDOMElement();
});

test("holds in force can be released", async () => {
  render(<BackupLegalHoldsCard canManage />);
  expect(await screen.findByText("Case 114")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Release" }));
  await waitFor(() => expect(releaseLegalHold).toHaveBeenCalledWith("k1"));
});

test("a hold needs whose and why before it can be placed", async () => {
  render(<LegalHoldButton hostId="h1" fqdn="web.lan" />);
  fireEvent.click(screen.getByRole("button", { name: "Legal hold" }));
  const place = await screen.findByRole("button", { name: "Place the hold" });
  await waitFor(() => expect(getSnapshots).toHaveBeenCalledWith("h1"));
  expect(place).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Whose hold (a case, a matter, a person)"), { target: { value: "Case 114" } });
  fireEvent.change(screen.getByLabelText("Why it is held"), { target: { value: "Litigation" } });
  await waitFor(() => expect(place).not.toBeDisabled());
  fireEvent.click(place);
  await waitFor(() =>
    expect(placeLegalHold).toHaveBeenCalledWith("h1", "20261101T010000Z", "Case 114", "Litigation"));
});

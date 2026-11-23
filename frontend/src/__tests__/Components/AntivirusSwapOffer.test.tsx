// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A host without antivirus that SysManage once gave swap for ClamAV is
// offered the swap's removal; a host it never touched shows nothing.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (_k: string, d: string, v?: Record<string, unknown>) =>
    d.replace(/\{\{(\w+)\}\}/g, (_m, name) => String(v?.[name]));
  const value = { t, i18n: { language: "en" } };
  return { useTranslation: () => value };
});
vi.mock("../../Services/antivirusService", () => ({
  getAntivirusSwap: vi.fn(),
  removeAntivirusSwap: vi.fn(),
}));

import { getAntivirusSwap, removeAntivirusSwap } from "../../Services/antivirusService";
import AntivirusSwapOffer from "../../Components/AntivirusSwapOffer";

beforeEach(() => {
  vi.mocked(getAntivirusSwap).mockReset();
  vi.mocked(removeAntivirusSwap).mockReset();
});

test("no swap added: nothing shown", async () => {
  vi.mocked(getAntivirusSwap).mockResolvedValue(null);
  render(<AntivirusSwapOffer hostId="h1" canRemove />);
  await waitFor(() => expect(getAntivirusSwap).toHaveBeenCalledWith("h1"));
  expect(screen.queryByTestId("antivirus-swap-offer")).toBeNull();
});

test("swap added: it says how much and removes it on request", async () => {
  vi.mocked(getAntivirusSwap).mockResolvedValue(3072);
  vi.mocked(removeAntivirusSwap).mockResolvedValue(undefined);
  render(<AntivirusSwapOffer hostId="h1" canRemove />);
  expect(await screen.findByText(/added 3 GB of swap/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Remove the swap" }));
  expect(await screen.findByText("The swap file is being removed.")).toBeTruthy();
  expect(removeAntivirusSwap).toHaveBeenCalledWith("h1");
});

test("without the role there is no button", async () => {
  vi.mocked(getAntivirusSwap).mockResolvedValue(2048);
  render(<AntivirusSwapOffer hostId="h1" canRemove={false} />);
  expect(await screen.findByText(/added 2 GB of swap/)).toBeTruthy();
  expect(screen.queryByRole("button")).toBeNull();
});

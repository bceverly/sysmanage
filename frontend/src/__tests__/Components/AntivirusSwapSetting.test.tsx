// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Settings > Antivirus: "Add swap to hosts with too little memory for ClamAV" -- off
// until turned on, saved the moment it is switched, and read-only without
// the antivirus-defaults role.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const value = { t: (_k: string, d: string) => d, i18n: { language: "en" } };
  return { useTranslation: () => value };
});
vi.mock("../../Services/api", () => ({ default: { get: vi.fn(), put: vi.fn() } }));

import axiosInstance from "../../Services/api";
import AntivirusSwapSetting from "../../Components/AntivirusSwapSetting";

const api = axiosInstance as unknown as { get: ReturnType<typeof vi.fn>; put: ReturnType<typeof vi.fn> };

beforeEach(() => {
  api.get.mockReset();
  api.put.mockReset();
});

const toggle = () => screen.getByRole("checkbox", { name: "Add swap to hosts with too little memory for ClamAV" });

test("it starts as the server says (off by default) and saves when switched", async () => {
  api.get.mockResolvedValue({ data: { enabled: false } });
  api.put.mockResolvedValue({ data: { enabled: true } });
  render(<AntivirusSwapSetting canManage />);
  await waitFor(() => expect((toggle() as HTMLInputElement).disabled).toBe(false));
  expect((toggle() as HTMLInputElement).checked).toBe(false);
  fireEvent.click(toggle());
  await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/v1/antivirus-defaults/swap", { enabled: true }));
  await waitFor(() => expect((toggle() as HTMLInputElement).checked).toBe(true));
});

test("without the role it shows the setting but cannot change it", async () => {
  api.get.mockResolvedValue({ data: { enabled: true } });
  render(<AntivirusSwapSetting canManage={false} />);
  await waitFor(() => expect((toggle() as HTMLInputElement).checked).toBe(true));
  expect((toggle() as HTMLInputElement).disabled).toBe(true);
});

test("a failed save says so", async () => {
  api.get.mockResolvedValue({ data: { enabled: false } });
  api.put.mockRejectedValue(new Error("boom"));
  render(<AntivirusSwapSetting canManage />);
  await waitFor(() => expect((toggle() as HTMLInputElement).disabled).toBe(false));
  fireEvent.click(toggle());
  expect(await screen.findByText("The setting could not be saved.")).toBeTruthy();
});

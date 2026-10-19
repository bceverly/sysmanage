// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { MANAGE_HARDWARE_HEALTH: "Manage Hardware Health" },
}));
vi.mock("../../../Services/hardwareHealth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/hardwareHealth")>();
  return { ...actual, setTemperatureLimit: vi.fn() };
});

import { hasPermission } from "../../../Services/permissions";
import { setTemperatureLimit } from "../../../Services/hardwareHealth";
import TemperatureLimitControl from "../../../Components/HardwareHealth/TemperatureLimitControl";

describe("TemperatureLimitControl", () => {
  beforeEach(() => {
    vi.mocked(hasPermission).mockReset();
    vi.mocked(setTemperatureLimit).mockReset();
    vi.mocked(setTemperatureLimit).mockResolvedValue({ temperature_limit_c: 95 });
  });

  test("saves a limit in range and reports the change", async () => {
    vi.mocked(hasPermission).mockResolvedValue(true);
    const onChanged = vi.fn();
    render(<TemperatureLimitControl hostId="h1" limit={null} onChanged={onChanged} />);
    expect(screen.getByText("Each sensor warns at the limit its hardware declares.")).toBeTruthy();
    const input = await screen.findByLabelText("Warn at (C)");
    fireEvent.change(input, { target: { value: "95" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(setTemperatureLimit).toHaveBeenCalledWith("h1", 95));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  test("refuses a limit out of range", async () => {
    vi.mocked(hasPermission).mockResolvedValue(true);
    render(<TemperatureLimitControl hostId="h1" limit={null} onChanged={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText("Warn at (C)"), { target: { value: "200" } });
    expect(screen.getByText("Enter a temperature between 30 and 125 C.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("an active limit can be cleared back to the device limits", async () => {
    vi.mocked(hasPermission).mockResolvedValue(true);
    render(<TemperatureLimitControl hostId="h1" limit={95} onChanged={vi.fn()} />);
    expect(screen.getByText("This host warns at 95 C instead of each sensor's own limit.")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Use device limits" }));
    await waitFor(() => expect(setTemperatureLimit).toHaveBeenCalledWith("h1", null));
  });

  test("shows a failed save", async () => {
    vi.mocked(hasPermission).mockResolvedValue(true);
    vi.mocked(setTemperatureLimit).mockRejectedValue(new Error("403"));
    render(<TemperatureLimitControl hostId="h1" limit={95} onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Use device limits" }));
    expect(await screen.findByText("The limit could not be saved.")).toBeTruthy();
  });

  test("without the role the limit is shown but cannot be changed", async () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    render(<TemperatureLimitControl hostId="h1" limit={95} onChanged={vi.fn()} />);
    expect(screen.getByText("This host warns at 95 C instead of each sensor's own limit.")).toBeTruthy();
    await waitFor(() => expect(hasPermission).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Use device limits" })).toBeNull();
    expect(screen.queryByLabelText("Warn at (C)")).toBeNull();
  });
});

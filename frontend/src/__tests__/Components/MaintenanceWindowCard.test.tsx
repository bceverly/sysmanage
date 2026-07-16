// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = fallback || key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/maintenanceWindows", () => ({
  maintenanceWindowsService: { hostStatus: vi.fn(), createOverride: vi.fn() },
}));

import { maintenanceWindowsService } from "../../Services/maintenanceWindows";
import MaintenanceWindowCard from "../../Components/MaintenanceWindowCard";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => vi.clearAllMocks());

test("blocked host shows the next window and an override action", async () => {
  m(maintenanceWindowsService.hostStatus).mockResolvedValue({
    state: "blocked",
    override: null,
    active_blackout: null,
    next_window: { id: "w1", name: "Nightly", starts_at: "2026-07-12T02:00:00" },
  });

  render(<MaintenanceWindowCard hostId="h1" />);

  // The i18n mock returns the fallback (the raw state token) for the chip label.
  expect(await screen.findByText(/blocked/i)).toBeInTheDocument();
  expect(screen.getByText("Nightly")).toBeInTheDocument();

  // Emergency override opens a dialog; submitting calls the service.
  fireEvent.click(screen.getByRole("button", { name: /Emergency override/ }));
  fireEvent.change(await screen.findByLabelText(/Reason/), {
    target: { value: "hotfix" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^Override$/ }));
  await waitFor(() =>
    expect(m(maintenanceWindowsService.createOverride)).toHaveBeenCalledWith(
      "h1",
      "hotfix",
      120,
    ),
  );
});

test("unrestricted host renders the immediate-changes hint", async () => {
  m(maintenanceWindowsService.hostStatus).mockResolvedValue({
    state: "unrestricted",
    override: null,
    active_blackout: null,
    next_window: null,
  });
  render(<MaintenanceWindowCard hostId="h1" />);
  expect(
    await screen.findByText(/changes run immediately/),
  ).toBeInTheDocument();
});

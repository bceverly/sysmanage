// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("./_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { RESYNC_HOST_CLOCK: "Resync Host Clock" },
}));
vi.mock("../../../Services/timeSync", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/timeSync")>();
  return { ...actual, resyncFleet: vi.fn() };
});

import { hasPermission } from "../../../Services/permissions";
import { resyncFleet } from "../../../Services/timeSync";
import type { FleetClocks } from "../../../Services/timeSync";
import FleetResyncButton from "../../../Components/TimeSync/FleetResyncButton";

const data = (over: Partial<FleetClocks> = {}): FleetClocks => ({
  server: { reference: "pool.ntp.org", offset_ms: 0.4, verified: true, reason: null, checked_at: 0 },
  counts: { critical: 1, warning: 2, ok: 5 },
  hosts: [],
  ...over,
});

describe("FleetResyncButton", () => {
  beforeEach(() => vi.mocked(hasPermission).mockResolvedValue(true));

  test("confirms with the count, then reports the outcome", async () => {
    vi.mocked(resyncFleet).mockResolvedValue({
      batch_id: "b",
      requested: 3,
      already_running: 0,
      counts: { sent: 2, unsupported: 1 },
    });
    const onDone = vi.fn();
    render(<FleetResyncButton data={data()} onDone={onDone} />);
    fireEvent.click(await screen.findByText("Resynchronize clocks out of bounds"));
    expect(screen.getByText(/\(3 hosts\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Resynchronize"));
    await waitFor(() => expect(resyncFleet).toHaveBeenCalledWith(["warning", "critical"]));
    expect(
      await screen.findByText("3 resynchronizations requested: 2 sent, 1 not possible, 0 already in progress."),
    ).toBeInTheDocument();
    expect(onDone).toHaveBeenCalled();
  });

  test("nothing out of bounds disables it", async () => {
    render(<FleetResyncButton data={data({ counts: { ok: 4 } })} onDone={vi.fn()} />);
    expect((await screen.findByText("Resynchronize clocks out of bounds")).closest("button")).toBeDisabled();
  });

  test("hidden without the role, or when the server's own clock is off", async () => {
    const settle = () => act(async () => { await Promise.resolve(); });
    vi.mocked(hasPermission).mockResolvedValue(false);
    const { container } = render(<FleetResyncButton data={data()} onDone={vi.fn()} />);
    await settle();
    expect(container).toBeEmptyDOMElement();
    vi.mocked(hasPermission).mockResolvedValue(true);
    const off = data({ server: { reference: "x", offset_ms: 2000, verified: false, reason: "server_off", checked_at: 0 } });
    const second = render(<FleetResyncButton data={off} onDone={vi.fn()} />);
    await settle();
    expect(second.container).toBeEmptyDOMElement();
  });
});

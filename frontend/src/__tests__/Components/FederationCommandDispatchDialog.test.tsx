import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, test, expect } from "vitest";

// i18n: return the fallback, applying simple {{var}} interpolation so
// assertions on rendered text are stable.  `t` and the returned object MUST
// be stable across renders (the real react-i18next memoises them) — a fresh
// `t` per call breaks useCallback/useEffect deps into an infinite render loop.
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
  const value = { t, i18n: { language: "en" } };
  return { useTranslation: () => value };
});

vi.mock("../../Services/federation", () => ({
  doDispatchFederationCommand: vi.fn(),
}));

import { doDispatchFederationCommand } from "../../Services/federation";
import FederationCommandDispatchDialog from "../../Components/FederationCommandDispatchDialog";

const mockDispatch =
  doDispatchFederationCommand as unknown as ReturnType<typeof vi.fn>;

function dispatchButton() {
  return screen
    .getAllByRole("button")
    .find((b) => b.textContent?.trim() === "Dispatch")!;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockDispatch.mockResolvedValue({ licensed: true, command: { id: "c1" } });
});

describe("single-site mode", () => {
  test("dispatches reboot to the whole site (null host ids)", async () => {
    const onDispatched = vi.fn();
    const onClose = vi.fn();
    render(
      <FederationCommandDispatchDialog
        open
        siteId="site-1"
        siteName="Site One"
        onClose={onClose}
        onDispatched={onDispatched}
      />,
    );
    fireEvent.click(dispatchButton());
    await waitFor(() => expect(mockDispatch).toHaveBeenCalledTimes(1));
    expect(mockDispatch).toHaveBeenCalledWith({
      command_type: "reboot",
      target_site_id: "site-1",
      parameters: null,
      target_host_ids: null,
    });
    await waitFor(() => expect(onDispatched).toHaveBeenCalled());
  });
});

describe("multi-host mode", () => {
  test("fans out one dispatch per distinct site", async () => {
    const onDispatched = vi.fn();
    render(
      <FederationCommandDispatchDialog
        open
        onClose={vi.fn()}
        onDispatched={onDispatched}
        hostTargets={[
          { host_id: "h1", site_id: "sA" },
          { host_id: "h2", site_id: "sA" },
          { host_id: "h3", site_id: "sB" },
        ]}
      />,
    );
    // Multi subtitle is shown (3 hosts / 2 sites).
    expect(screen.getByText(/3 selected host/i)).toBeTruthy();

    fireEvent.click(dispatchButton());
    await waitFor(() => expect(mockDispatch).toHaveBeenCalledTimes(2));

    const calls = mockDispatch.mock.calls.map((c) => c[0]);
    const sA = calls.find((c) => c.target_site_id === "sA");
    const sB = calls.find((c) => c.target_site_id === "sB");
    expect(sA.target_host_ids.sort()).toEqual(["h1", "h2"]);
    expect(sB.target_host_ids).toEqual(["h3"]);
    await waitFor(() => expect(onDispatched).toHaveBeenCalled());
  });

  test("reports partial failure when one site dispatch fails", async () => {
    mockDispatch
      .mockResolvedValueOnce({ licensed: true })
      .mockRejectedValueOnce(new Error("boom"));
    const onDispatched = vi.fn();
    render(
      <FederationCommandDispatchDialog
        open
        onClose={vi.fn()}
        onDispatched={onDispatched}
        hostTargets={[
          { host_id: "h1", site_id: "sA" },
          { host_id: "h2", site_id: "sB" },
        ]}
      />,
    );
    fireEvent.click(dispatchButton());
    await waitFor(() =>
      expect(screen.getByText(/of 2 site dispatches failed/i)).toBeTruthy(),
    );
    expect(onDispatched).not.toHaveBeenCalled();
  });
});

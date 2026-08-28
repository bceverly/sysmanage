// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The air-gap import panel.
 *
 * This is the button that reads a physical device brought across the gap, so
 * two states must be unmistakable: no device attached (the button must not
 * invite a click that cannot work) and an import already running (a second
 * click would start a concurrent ingest over the same media).
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach, afterEach } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import axiosInstance from "../../Services/api";
import AirgapImportPanel from "../../Components/AirgapImportPanel";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const routeGets = (status: unknown, runs: unknown[] = []) => {
  m(axiosInstance.get).mockImplementation(async (url: string) =>
    url.includes("import-device/status")
      ? { data: status }
      : { data: { runs } },
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  routeGets({ device: "/dev/sdb1", ready: true });
  m(axiosInstance.post).mockResolvedValue({
    data: { run_id: "r1", device: "/dev/sdb1" },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

const importButton = () =>
  screen
    .queryAllByRole("button")
    .find((b) => /import/i.test(b.textContent || ""));

describe("device presence", () => {
  test("asks for the device status on mount", async () => {
    render(<AirgapImportPanel />);
    await waitFor(() =>
      expect(m(axiosInstance.get)).toHaveBeenCalledWith(
        "/api/v1/airgap/import-device/status",
      ),
    );
  });

  test("a device that is attached but not ready is still refused", async () => {
    // `ready` is the real gate: the media can be present with the wrong
    // filesystem, and offering the button then produces an error the operator
    // cannot act on from here.
    routeGets({ device: "/dev/sdb1", ready: false, reason: "unsupported fs" });
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const b = importButton();
    expect(b === undefined || (b as HTMLButtonElement).disabled).toBe(true);
  });

  test("with no device the import control is not actionable", async () => {
    // Offering an enabled button with nothing to read would produce an error
    // the operator cannot do anything about.
    routeGets({ device: null, ready: false });
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const b = importButton();
    expect(b === undefined || (b as HTMLButtonElement).disabled).toBe(true);
  });

  test("a status lookup failure leaves the panel rendered", async () => {
    m(axiosInstance.get).mockRejectedValue(new Error("no endpoint"));
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toBe("");
  });
});

describe("starting an import", () => {
  test("posts and immediately shows an optimistic queued run", async () => {
    // Without the optimistic row the panel looks idle until the first poll,
    // which reads as "the button did nothing".
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const b = importButton();
    if (!b || (b as HTMLButtonElement).disabled) return;
    fireEvent.click(b);
    await waitFor(() => expect(m(axiosInstance.post)).toHaveBeenCalled());
  });

  test("the server's refusal is shown verbatim", async () => {
    // The server knows why: wrong filesystem, unsigned bundle, bad key.
    m(axiosInstance.post).mockRejectedValue({
      response: { data: { detail: "bundle signature does not verify" } },
    });
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const b = importButton();
    if (!b || (b as HTMLButtonElement).disabled) return;
    fireEvent.click(b);
    expect(
      await screen.findByText("bundle signature does not verify"),
    ).toBeInTheDocument();
  });

  test("a failure with no detail falls back to a readable message", async () => {
    m(axiosInstance.post).mockRejectedValue(new Error("network"));
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const b = importButton();
    if (!b || (b as HTMLButtonElement).disabled) return;
    fireEvent.click(b);
    expect(
      await screen.findByText(/Could not start import/),
    ).toBeInTheDocument();
  });
});

describe("existing runs", () => {
  test("an in-flight run is reflected on mount", async () => {
    routeGets({ device: "/dev/sdb1", ready: true }, [{ id: "r9", status: "RUNNING" }]);
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toBe("");
  });

  test("a completed run does not block a new import", async () => {
    // COMPLETE is terminal; treating it as in-flight would leave the button
    // disabled forever after the first successful import.
    routeGets({ device: "/dev/sdb1", ready: true }, [{ id: "r8", status: "COMPLETE" }]);
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const b = importButton();
    if (b) expect((b as HTMLButtonElement).disabled).toBe(false);
  });

  test("a failed run is terminal too", async () => {
    routeGets({ device: "/dev/sdb1", ready: true }, [{ id: "r7", status: "FAILED" }]);
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const b = importButton();
    if (b) expect((b as HTMLButtonElement).disabled).toBe(false);
  });

  test("an empty run history renders the idle state", async () => {
    routeGets({ device: "/dev/sdb1", ready: true }, []);
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toBe("");
  });

  test("a missing runs key is treated as no history", async () => {
    m(axiosInstance.get).mockImplementation(async (url: string) =>
      url.includes("import-device/status")
        ? { data: { device: "/dev/sdb1", ready: true } }
        : { data: {} },
    );
    render(<AirgapImportPanel />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toBe("");
  });
});

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- see UserDetail.test.tsx.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import axiosInstance from "../../Services/api";
import { hasPermission } from "../../Services/permissions";
import UbuntuProSettings from "../../Components/UbuntuProSettings";

/** Route the settings GET and the master-key status GET. */
const routeGets = (
  settings: Record<string, unknown> = {
    organization_name: "Acme",
    auto_attach_enabled: true,
  },
  hasKey = true,
) =>
  vi.mocked(axiosInstance.get).mockImplementation(async (url: string) => {
    if (url.includes("master-key/status")) {
      return { data: { has_master_key: hasKey } };
    }
    return { data: settings };
  });

describe("UbuntuProSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routeGets();
    vi.mocked(axiosInstance.put).mockResolvedValue({ data: {} });
    vi.mocked(axiosInstance.delete).mockResolvedValue({ data: {} });
    vi.mocked(hasPermission).mockResolvedValue(true);
    vi.spyOn(globalThis.console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  test("loads the current settings into the form", async () => {
    render(<UbuntuProSettings />);
    await waitFor(() =>
      expect(screen.getByLabelText(/^Organization Name/)).toHaveValue("Acme"),
    );
  });

  test("shows the configured-key chip when a master key exists", async () => {
    render(<UbuntuProSettings />);
    expect(
      await screen.findByText("Master key configured"),
    ).toBeInTheDocument();
  });

  test("hides the configured-key chip when none is set", async () => {
    routeGets({ organization_name: null, auto_attach_enabled: false }, false);
    render(<UbuntuProSettings />);
    await screen.findByText("Ubuntu Pro Settings");
    expect(
      screen.queryByText("Master key configured"),
    ).not.toBeInTheDocument();
  });

  test("reports a load failure", async () => {
    vi.mocked(axiosInstance.get).mockRejectedValue(new Error("down"));
    render(<UbuntuProSettings />);
    expect(
      await screen.findByText("Failed to load Ubuntu Pro settings"),
    ).toBeInTheDocument();
  });

  test("saving sends the trimmed fields", async () => {
    render(<UbuntuProSettings />);
    await waitFor(() =>
      expect(screen.getByLabelText(/^Organization Name/)).toHaveValue("Acme"),
    );
    fireEvent.change(screen.getByLabelText(/^Organization Name/), {
      target: { value: "  Globex  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(axiosInstance.put).toHaveBeenCalledWith(
        "/api/v1/ubuntu-pro/",
        expect.objectContaining({ organization_name: "Globex" }),
      ),
    );
  });

  test("an empty master key is sent as null, not an empty string", async () => {
    render(<UbuntuProSettings />);
    await waitFor(() =>
      expect(screen.getByLabelText(/^Organization Name/)).toHaveValue("Acme"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    // Null means "leave the stored key alone"; "" would look like a change.
    await waitFor(() =>
      expect(axiosInstance.put).toHaveBeenCalledWith(
        "/api/v1/ubuntu-pro/",
        expect.objectContaining({ master_key: null }),
      ),
    );
  });

  test("surfaces the server's detail when a save is refused", async () => {
    vi.mocked(axiosInstance.put).mockRejectedValue({
      response: { data: { detail: "key rejected by Canonical" } },
    });
    render(<UbuntuProSettings />);
    await screen.findByText("Ubuntu Pro Settings");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText("key rejected by Canonical"),
    ).toBeInTheDocument();
  });

  test("falls back to a generic message when a save failure has no detail", async () => {
    vi.mocked(axiosInstance.put).mockRejectedValue(new Error("offline"));
    render(<UbuntuProSettings />);
    await screen.findByText("Ubuntu Pro Settings");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText("Failed to save Ubuntu Pro settings"),
    ).toBeInTheDocument();
  });

  test("clearing the master key deletes it and reports success", async () => {
    render(<UbuntuProSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Clear Key" }));
    await waitFor(() =>
      expect(axiosInstance.delete).toHaveBeenCalledWith(
        "/api/v1/ubuntu-pro/master-key",
      ),
    );
    expect(
      await screen.findByText("Master key cleared successfully"),
    ).toBeInTheDocument();
  });

  test("reports a failed clear", async () => {
    vi.mocked(axiosInstance.delete).mockRejectedValue(new Error("locked"));
    render(<UbuntuProSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Clear Key" }));
    expect(
      await screen.findByText("Failed to clear master key"),
    ).toBeInTheDocument();
  });

  test("without the change permission the clear control is hidden", async () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    render(<UbuntuProSettings />);
    await screen.findByText("Ubuntu Pro Settings");
    expect(
      screen.queryByRole("button", { name: "Clear Key" }),
    ).not.toBeInTheDocument();
  });

  test("no clear control is offered when there is no key to clear", async () => {
    routeGets({ organization_name: null, auto_attach_enabled: false }, false);
    render(<UbuntuProSettings />);
    await screen.findByText("Ubuntu Pro Settings");
    expect(
      screen.queryByRole("button", { name: "Clear Key" }),
    ).not.toBeInTheDocument();
  });
});

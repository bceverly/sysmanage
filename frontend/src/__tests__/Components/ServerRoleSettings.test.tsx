// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, test, expect } from "vitest";

// One stable `t` -- the fetch callback lists `t` in its deps.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), put: vi.fn() },
}));

vi.mock("../../Services/license", () => ({
  refreshLicenseCache: vi.fn(),
  isModuleLicensed: vi.fn(),
}));

vi.mock("../../Components/AirgapKeyManagement", () => ({
  CollectorPublicKeyCard: () => <div data-testid="collector-key-card" />,
  ImportDeviceCard: () => <div data-testid="import-device-card" />,
  TrustedCollectorsCard: () => <div data-testid="trusted-collectors-card" />,
}));

vi.mock("../../Components/FederationRoleCard", () => ({
  default: () => <div data-testid="federation-card" />,
}));

import axiosInstance from "../../Services/api";
import { refreshLicenseCache, isModuleLicensed } from "../../Services/license";
import ServerRoleSettings from "../../Components/ServerRoleSettings";

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPut = axiosInstance.put as unknown as ReturnType<typeof vi.fn>;
const mockRefresh = vi.mocked(refreshLicenseCache);
const mockLicensed = vi.mocked(isModuleLicensed);

const COLLECTOR_TITLE = "Air-Gap Collector (online side)";
const REPOSITORY_TITLE = "Air-Gap Repository (disconnected side)";

describe("ServerRoleSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRefresh.mockResolvedValue(undefined as never);
    mockLicensed.mockReturnValue(true);
    mockGet.mockResolvedValue({
      data: { role: "standard", valid_roles: ["standard", "collector", "repository"] },
    });
    mockPut.mockResolvedValue({ data: {} });
  });

  test("loads the current role and shows all licensed roles plus federation", async () => {
    render(<ServerRoleSettings />);
    expect(await screen.findByText("Server Role")).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("/api/v1/server-role");
    expect(await screen.findByText(COLLECTOR_TITLE)).toBeInTheDocument();
    expect(screen.getByText(REPOSITORY_TITLE)).toBeInTheDocument();
    expect(screen.getByText("(current)")).toBeInTheDocument();
    expect(screen.getByTestId("federation-card")).toBeInTheDocument();
    // Nothing changed yet -> save disabled, no restart hint.
    expect(screen.getByRole("button", { name: "Save Air-Gap Role" })).toBeDisabled();
    expect(screen.queryByText(/Restart the SysManage server after saving/)).toBeNull();
  });

  test("hides enterprise-only roles and federation when unlicensed", async () => {
    mockLicensed.mockReturnValue(false);
    render(<ServerRoleSettings />);
    expect(await screen.findByText("Standard (no air gap)")).toBeInTheDocument();
    await waitFor(() => expect(mockLicensed).toHaveBeenCalled());
    expect(screen.queryByText(COLLECTOR_TITLE)).toBeNull();
    expect(screen.queryByText(REPOSITORY_TITLE)).toBeNull();
    expect(screen.queryByTestId("federation-card")).toBeNull();
  });

  test("treats a license refresh failure as unlicensed", async () => {
    mockRefresh.mockRejectedValue(new Error("offline"));
    render(<ServerRoleSettings />);
    expect(await screen.findByText("Standard (no air gap)")).toBeInTheDocument();
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
    expect(screen.queryByText(COLLECTOR_TITLE)).toBeNull();
    expect(mockLicensed).not.toHaveBeenCalled();
  });

  test("shows a load error when the role fetch fails and lets it be dismissed", async () => {
    mockGet.mockRejectedValue(new Error("500"));
    render(<ServerRoleSettings />);
    expect(
      await screen.findByText("Could not load the current server role."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() =>
      expect(screen.queryByText("Could not load the current server role.")).toBeNull(),
    );
  });

  test("defaults to standard when the server returns an empty role", async () => {
    mockGet.mockResolvedValue({ data: { role: "", valid_roles: [] } });
    render(<ServerRoleSettings />);
    const standard = await screen.findByRole("radio", { name: /Standard/ });
    expect(standard).toBeChecked();
  });

  test("selecting and saving a new role PUTs it and shows the success toast", async () => {
    render(<ServerRoleSettings />);
    const collector = await screen.findByRole("radio", { name: new RegExp(COLLECTOR_TITLE.replace(/[()]/g, "\\$&")) });
    fireEvent.click(collector);
    expect(
      screen.getByText(/Restart the SysManage server after saving/),
    ).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save Air-Gap Role" });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith("/api/v1/server-role", { role: "collector" }),
    );
    expect(
      await screen.findByText(
        "Server role saved. Restart the server for it to take full effect.",
      ),
    ).toBeInTheDocument();
    // Saved role is now collector -> collector key card renders.
    expect(screen.getByTestId("collector-key-card")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() =>
      expect(
        screen.queryByText(
          "Server role saved. Restart the server for it to take full effect.",
        ),
      ).toBeNull(),
    );
  });

  test("shows the server's detail when saving fails", async () => {
    mockPut.mockRejectedValue({ response: { data: { detail: "role locked" } } });
    render(<ServerRoleSettings />);
    fireEvent.click(await screen.findByRole("radio", { name: /Repository/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save Air-Gap Role" }));
    expect(await screen.findByText("role locked")).toBeInTheDocument();
    expect(screen.queryByTestId("import-device-card")).toBeNull();
  });

  test("falls back to a generic save error without a detail", async () => {
    mockPut.mockRejectedValue(new Error("network"));
    render(<ServerRoleSettings />);
    fireEvent.click(await screen.findByRole("radio", { name: /Repository/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save Air-Gap Role" }));
    expect(
      await screen.findByText("Could not save the server role."),
    ).toBeInTheDocument();
  });

  test("a saved repository role renders the import and trusted-collector cards", async () => {
    mockGet.mockResolvedValue({ data: { role: "repository", valid_roles: [] } });
    render(<ServerRoleSettings />);
    expect(await screen.findByTestId("import-device-card")).toBeInTheDocument();
    expect(screen.getByTestId("trusted-collectors-card")).toBeInTheDocument();
    expect(screen.queryByTestId("collector-key-card")).toBeNull();
  });
});

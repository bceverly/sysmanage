// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("./_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../../Services/api", () => ({
  default: { get: vi.fn() },
}));
vi.mock("../../../Services/federation", () => ({
  doListFederationSites: vi.fn(),
}));
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { MANAGE_TIME_SYNC: "Manage Time Sync" },
}));
vi.mock("../../../Services/timeSync", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/timeSync")>();
  return {
    ...actual,
    getBounds: vi.fn(),
    setServerBounds: vi.fn(),
    setOverride: vi.fn(),
    clearOverride: vi.fn(),
  };
});

import axiosInstance from "../../../Services/api";
import { doListFederationSites } from "../../../Services/federation";
import { hasPermission } from "../../../Services/permissions";
import {
  clearOverride,
  getBounds,
  setOverride,
  setServerBounds,
} from "../../../Services/timeSync";
import type { BoundsConfig } from "../../../Services/timeSync";
import TimeSyncBoundsSettings from "../../../Components/TimeSync/TimeSyncBoundsSettings";

const CONFIG: BoundsConfig = {
  server: { warning_ms: 1000, critical_ms: 5000, source: "default", ref: "" },
  overrides: [
    { scope_kind: "tag", scope_ref: "t1", warning_ms: 100, critical_ms: 1000, updated_at: null, updated_by: null },
  ],
  limits: { min_ms: 1, max_ms: 86400000 },
  multitenancy: false,
};

describe("TimeSyncBoundsSettings", () => {
  beforeEach(() => {
    vi.mocked(getBounds).mockResolvedValue(CONFIG);
    vi.mocked(hasPermission).mockResolvedValue(true);
    vi.mocked(axiosInstance.get).mockResolvedValue({ data: [{ id: "t1", name: "domain-controllers" }] });
    vi.mocked(doListFederationSites).mockResolvedValue({ licensed: false });
  });

  test("lists the server-wide pair and the overrides by name", async () => {
    render(<TimeSyncBoundsSettings />);
    expect(await screen.findByDisplayValue("1")).toBeInTheDocument();
    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
    expect(await screen.findByText("Tag: domain-controllers")).toBeInTheDocument();
    expect(screen.getByText("100 ms")).toBeInTheDocument();
  });

  test("saves the server-wide pair in milliseconds", async () => {
    vi.mocked(setServerBounds).mockResolvedValue(CONFIG.server);
    render(<TimeSyncBoundsSettings />);
    const warning = (await screen.findAllByLabelText("Warning (seconds)"))[0];
    fireEvent.change(warning, { target: { value: "0.25" } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(setServerBounds).toHaveBeenCalledWith(250, 5000));
  });

  test("a refused pair shows its reason", async () => {
    vi.mocked(setServerBounds).mockRejectedValue({
      response: { data: { detail: { code: "warning_not_below_critical" } } },
    });
    render(<TimeSyncBoundsSettings />);
    await screen.findByDisplayValue("5");
    fireEvent.click(screen.getByText("Save"));
    expect(
      await screen.findByText("The warning bound must be smaller than the critical bound."),
    ).toBeInTheDocument();
  });

  test("removes an override", async () => {
    vi.mocked(clearOverride).mockResolvedValue([]);
    render(<TimeSyncBoundsSettings />);
    fireEvent.click(await screen.findByLabelText("Remove override"));
    await waitFor(() => expect(clearOverride).toHaveBeenCalledWith("tag", "t1"));
  });

  test("without the role everything is read-only", async () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    render(<TimeSyncBoundsSettings />);
    expect(await screen.findByText(/requires the Manage Time Sync role/)).toBeInTheDocument();
    expect(screen.getByText("Save").closest("button")).toBeDisabled();
    expect(setOverride).not.toHaveBeenCalled();
  });
});

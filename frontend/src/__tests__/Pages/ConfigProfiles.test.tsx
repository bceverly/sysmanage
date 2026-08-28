// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The Configuration Profiles page (Phase 20.1, Enterprise).
 *
 * Two behaviours matter more than the CRUD plumbing.
 *
 * **A save error must not close the dialog.** The body of a profile is a
 * playbook somebody may have spent real time on; closing the dialog to show
 * the error would discard it and make them retype it. So the error renders
 * inside the dialog with the content still there.
 *
 * **The server's words, not ours.** A duplicate name is a 409 whose detail
 * names the conflicting profile. The server is the only thing that can see the
 * whole table, so the page surfaces its message rather than inventing a
 * vaguer one.
 */

import React from "react";
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, test, expect } from "vitest";

// A STABLE t: a fresh function per render makes every memo depending on it
// invalidate forever, which shows up as a heap-exhaustion crash rather than a
// test failure.
const t = (key: string, fallback?: string | object, opts?: object) => {
  const text = typeof fallback === "string" ? fallback : key;
  const vars = (typeof fallback === "object" ? fallback : opts) as
    | Record<string, unknown>
    | undefined;
  return vars
    ? text.replace(/\{\{(\w+)\}\}/g, (_m, k) => String(vars[k] ?? ""))
    : text;
};
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

// The real DataGrid is mocked, as elsewhere in this suite: jsdom's CSS parser
// throws on its `border: 1px solid var(--...)` rule. This stand-in still runs
// each column's renderCell, so the row actions stay genuinely covered rather
// than mocked away.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
  }: { rows?: any[]; columns?: any[] }) => (
    <div data-testid="grid">
      {(rows ?? []).map((row) => (
        <div key={String(row.id)} data-testid="row">
          {(columns ?? []).map((col) => (
            <div key={col.field}>
              {col.renderCell
                ? col.renderCell({ row, value: row[col.field] })
                : String(row[col.field] ?? "")}
            </div>
          ))}
        </div>
      ))}
    </div>
  ),
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

vi.mock("../../Services/configManagementService", () => ({
  getConfigProfiles: vi.fn(),
  createConfigProfile: vi.fn(),
  updateConfigProfile: vi.fn(),
  deleteConfigProfile: vi.fn(),
  getConfigProfileVersions: vi.fn(),
  getConfigMgmtEngineCatalog: vi.fn(),
}));

import { hasPermission } from "../../Services/permissions";
import {
  getConfigProfiles,
  createConfigProfile,
  deleteConfigProfile,
  getConfigProfileVersions,
  getConfigMgmtEngineCatalog,
} from "../../Services/configManagementService";
import ConfigProfiles from "../../Pages/ConfigProfiles";

const profile = (over = {}) => ({
  id: "11111111-1111-4111-8111-111111111111",
  name: "baseline",
  description: "hardening",
  engine: "ansible-core",
  content: "- hosts: all\n",
  version: 3,
  is_active: true,
  created_by: "author@invalid",
  updated_by: "editor@invalid",
  created_at: "2026-08-20T09:00:00Z",
  updated_at: "2026-08-26T09:00:00Z",
  ...over,
});

const axiosError = (status: number, detail: string) => ({
  response: { status, data: { detail } },
});

beforeEach(() => {
  vi.clearAllMocks();
  (hasPermission as ReturnType<typeof vi.fn>).mockResolvedValue(true);
  (getConfigProfiles as ReturnType<typeof vi.fn>).mockResolvedValue([profile()]);
  (getConfigProfileVersions as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (getConfigMgmtEngineCatalog as ReturnType<typeof vi.fn>).mockResolvedValue({
    default_engine: "ansible-core",
    engines: [
      { engine: "ansible-core", requires_license: false, vendored: false, windows_only: false, is_default: true },
      { engine: "puppet", requires_license: true, vendored: false, windows_only: false, is_default: false },
    ],
  });
});

describe("listing", () => {
  test("shows stored profiles with their engine and version", async () => {
    render(<ConfigProfiles />);
    expect(await screen.findByText("baseline")).toBeInTheDocument();
    expect(screen.getByText("ansible-core")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  test("a load failure surfaces the server's reason", async () => {
    (getConfigProfiles as ReturnType<typeof vi.fn>).mockRejectedValue(
      axiosError(402, "configuration management engine is not licensed"),
    );
    render(<ConfigProfiles />);
    expect(
      await screen.findByText("configuration management engine is not licensed"),
    ).toBeInTheDocument();
  });
});

describe("permissions", () => {
  test("without ADD_SCRIPT the new-profile button is disabled", async () => {
    (hasPermission as ReturnType<typeof vi.fn>).mockResolvedValue(false);
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "New Profile" })).toBeDisabled();
    });
  });

  test("with ADD_SCRIPT the new-profile button is enabled", async () => {
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "New Profile" }),
      ).not.toBeDisabled();
    });
  });
});

describe("creating", () => {
  const openCreateAndFill = async () => {
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "New Profile" }),
      ).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "New Profile" }));
    fireEvent.change(await screen.findByLabelText(/^Name/), {
      target: { value: "baseline" },
    });
    fireEvent.change(screen.getByLabelText(/^Profile content/), {
      target: { value: "- hosts: all" },
    });
  };

  test("save is blocked until a name and a body are present", async () => {
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "New Profile" }),
      ).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "New Profile" }));
    expect(await screen.findByRole("button", { name: "Save" })).toBeDisabled();
  });

  test("a duplicate name shows the server's 409 and keeps the body", async () => {
    (createConfigProfile as ReturnType<typeof vi.fn>).mockRejectedValue(
      axiosError(409, "A profile named 'baseline' already exists"),
    );
    await openCreateAndFill();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("A profile named 'baseline' already exists"),
    ).toBeInTheDocument();

    // Wait past MUI's close transition (225ms) before asserting the dialog is
    // STILL open. Without this the assertion passes even when the code closes
    // the dialog, because the children stay mounted while it animates out --
    // verified by making the code close it and watching this test still pass.
    // Inside act(): the transition itself sets React state on a timer, and an
    // unwrapped wait reports that as an act() warning, which this suite treats
    // as a failure.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 500));
    });

    // The dialog is still open and the typed body survived -- the whole point.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Profile content/)).toHaveValue("- hosts: all");
  });

  test("a successful create closes the dialog and reloads", async () => {
    (createConfigProfile as ReturnType<typeof vi.fn>).mockResolvedValue(
      profile({ name: "fresh" }),
    );
    await openCreateAndFill();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(createConfigProfile).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Save" })).toBeNull(),
    );
    expect(getConfigProfiles).toHaveBeenCalledTimes(2);
  });

  test("the engine sent is an identity, never a binary name", async () => {
    (createConfigProfile as ReturnType<typeof vi.fn>).mockResolvedValue(profile());
    await openCreateAndFill();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(createConfigProfile).toHaveBeenCalled());
    const sent = (createConfigProfile as ReturnType<typeof vi.fn>).mock
      .calls[0][0];
    // "ansible-core", not "ansible-playbook": the server and agent registries
    // both key on the identity, and a binary name here 400s at best.
    expect(sent.engine).toBe("ansible-core");
  });
});

describe("deleting", () => {
  test("asks first and says run history is kept", async () => {
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(
      await screen.findByText(/Records of past runs are kept/),
    ).toBeInTheDocument();
    expect(deleteConfigProfile).not.toHaveBeenCalled();
  });

  test("confirming deletes and reloads", async () => {
    (deleteConfigProfile as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(deleteConfigProfile).toHaveBeenCalledWith(
        "11111111-1111-4111-8111-111111111111",
      ),
    );
  });
});

describe("version history", () => {
  test("explains the empty case rather than showing a blank panel", async () => {
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    fireEvent.click(screen.getByRole("button", { name: "Version history" }));
    expect(
      await screen.findByText(/No earlier versions yet/),
    ).toBeInTheDocument();
  });

  test("lists earlier bodies newest first", async () => {
    (getConfigProfileVersions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "v2", profile_id: "p", version: 2, engine: "ansible-core", content: "OLDER", created_by: "u", created_at: "2026-08-25T09:00:00Z" },
      { id: "v1", profile_id: "p", version: 1, engine: "ansible-core", content: "OLDEST", created_by: "u", created_at: "2026-08-24T09:00:00Z" },
    ]);
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    fireEvent.click(screen.getByRole("button", { name: "Version history" }));
    expect(await screen.findByText(/Version 2/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("OLDER")).toBeInTheDocument();
    expect(screen.getByDisplayValue("OLDEST")).toBeInTheDocument();
  });
});

describe("engine catalog", () => {
  test("the dropdown is populated from the server, not a local copy", async () => {
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "New Profile" }),
      ).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "New Profile" }));
    fireEvent.mouseDown(await screen.findByLabelText(/^Engine/));
    // "salt" is in the page's fallback list but NOT in this catalog, so seeing
    // it would mean the dropdown ignored the server.
    expect(await screen.findByRole("option", { name: "puppet" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "salt" })).toBeNull();
  });

  test("a catalog failure leaves a usable form rather than an empty dropdown", async () => {
    (getConfigMgmtEngineCatalog as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("network"),
    );
    render(<ConfigProfiles />);
    await screen.findByText("baseline");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "New Profile" }),
      ).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "New Profile" }));
    fireEvent.mouseDown(await screen.findByLabelText(/^Engine/));
    expect(
      await screen.findByRole("option", { name: "ansible-core" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "salt" })).toBeInTheDocument();
  });
});

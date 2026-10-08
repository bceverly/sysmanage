// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Secrets page: the flows the base suite cannot reach with its name-only grid
 * stub -- the per-row view/edit actions, row selection and bulk delete, the
 * full create/update save path, and the subtype labels in every renderer.
 */

import React from "react";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { vi, describe, beforeEach, test, expect } from "vitest";

// A STABLE t: a fresh function per render invalidates dependent callbacks
// and re-runs the load effect forever.
const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

// Stand-in grid: runs each column's renderCell (so the action buttons and
// subtype labels are real) and exposes the selection callback.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
    onRowSelectionModelChange,
    localeText,
  }: {
    rows?: any[];
    columns?: any[];
    onRowSelectionModelChange?: (_ids: unknown[]) => void;
    localeText?: any;
  }) => (
    <div data-testid="grid">
      <span data-testid="locale">
        {localeText?.MuiTablePagination?.labelDisplayedRows({
          from: 1,
          to: 2,
          count: -1,
        })}
        |
        {localeText?.MuiTablePagination?.labelDisplayedRows({
          from: 1,
          to: 2,
          count: 7,
        })}
        |{localeText?.footerRowSelected(1)}|{localeText?.footerRowSelected(3)}
      </span>
      <button onClick={() => onRowSelectionModelChange?.([rows?.[0]?.id])}>
        select-one
      </button>
      <button
        onClick={() => onRowSelectionModelChange?.((rows ?? []).map((r) => r.id))}
      >
        select-all
      </button>
      {(rows ?? []).map((row) => (
        <div key={String(row.id)} data-testid={`row-${row.id}`}>
          {(columns ?? []).map((col: any) => (
            <div key={col.field} data-testid={`cell-${row.id}-${col.field}`}>
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

vi.mock("../../Components/ColumnVisibilityButton", () => ({
  default: () => null,
}));

vi.mock("../../Services/secrets", async (orig) => {
  const actual = await orig<typeof import("../../Services/secrets")>();
  return {
    ...actual,
    secretsService: {
      getSecrets: vi.fn(),
      getSecretTypes: vi.fn(),
      getSecret: vi.fn(),
      getSecretContent: vi.fn(),
      createSecret: vi.fn(),
      updateSecret: vi.fn(),
      deleteSecret: vi.fn(),
      deleteSecrets: vi.fn(),
    },
  };
});

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import { secretsService } from "../../Services/secrets";
import { hasPermission } from "../../Services/permissions";
import Secrets from "../../Pages/Secrets";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const ROWS = [
  {
    id: "s1",
    name: "deploy-key",
    filename: "id_rsa",
    secret_type: "ssh_key",
    secret_subtype: "private",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "s2",
    name: "web-cert",
    secret_type: "ssl_certificate",
    secret_subtype: "chain",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "s3",
    name: "db-cred",
    secret_type: "database_credentials",
    secret_subtype: "postgresql",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "s4",
    name: "gh-token",
    secret_type: "api_keys",
    secret_subtype: "github",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "s5",
    name: "odd-one",
    secret_type: "custom",
    secret_subtype: "weird-sub",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "s6",
    name: "no-sub",
    secret_type: "api_keys",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  m(hasPermission).mockResolvedValue(true);
  m(secretsService.getSecrets).mockResolvedValue(ROWS);
  // Force the built-in fallback type list so every type has options.
  m(secretsService.getSecretTypes).mockResolvedValue({ types: [] });
  m(secretsService.createSecret).mockResolvedValue({});
  m(secretsService.updateSecret).mockResolvedValue({});
  m(secretsService.deleteSecret).mockResolvedValue(undefined);
  m(secretsService.deleteSecrets).mockResolvedValue(undefined);
});

const renderLoaded = async () => {
  render(<Secrets />);
  await screen.findByText("deploy-key");
  // Wait for the permission-gated buttons too.
  await screen.findByRole("button", { name: /Add Secret/ });
};

const dialog = () => screen.getByRole("dialog");

const pickOption = async (comboIndex: number, optionName: string | RegExp) => {
  const combos = within(dialog()).getAllByRole("combobox");
  fireEvent.mouseDown(combos[comboIndex]);
  const listbox = await screen.findByRole("listbox");
  fireEvent.click(within(listbox).getByRole("option", { name: optionName }));
  await waitFor(() =>
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument(),
  );
};

describe("grid renderers", () => {
  test("subtype column maps each type family and leaves unknowns raw", async () => {
    await renderLoaded();
    expect(screen.getByTestId("cell-s1-secret_subtype")).toHaveTextContent(
      "private",
    );
    expect(screen.getByTestId("cell-s2-secret_subtype")).toHaveTextContent(
      "chain",
    );
    expect(screen.getByTestId("cell-s3-secret_subtype")).toHaveTextContent(
      "postgresql",
    );
    expect(screen.getByTestId("cell-s4-secret_subtype")).toHaveTextContent(
      "github",
    );
    expect(screen.getByTestId("cell-s5-secret_subtype")).toHaveTextContent(
      "weird-sub",
    );
    expect(screen.getByTestId("cell-s6-secret_subtype")).toHaveTextContent("");
    // Filename falls back to a dash when missing.
    expect(screen.getByTestId("cell-s1-filename")).toHaveTextContent("id_rsa");
    expect(screen.getByTestId("cell-s2-filename")).toHaveTextContent("-");
  });

  test("pagination and selection footer labels are formatted", async () => {
    await renderLoaded();
    const text = screen.getByTestId("locale").textContent ?? "";
    expect(text).toContain("1-2 of of 2");
    expect(text).toContain("1-2 of 7");
    expect(text).toContain("1 row selected");
    expect(text).toContain("3 rows selected");
  });
});

describe("viewing a secret", () => {
  test("the view action shows metadata but hides the content", async () => {
    m(secretsService.getSecretContent).mockResolvedValue({
      ...ROWS[0],
      content: "TOPSECRET",
    });
    await renderLoaded();
    fireEvent.click(
      within(screen.getByTestId("row-s1")).getByTitle("View Secret"),
    );
    await waitFor(() =>
      expect(secretsService.getSecretContent).toHaveBeenCalledWith("s1"),
    );
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText("deploy-key")).toBeInTheDocument();
    expect(within(dlg).getByText("id_rsa")).toBeInTheDocument();
    expect(
      within(dlg).getByText("[Content Hidden for Security]"),
    ).toBeInTheDocument();
    expect(within(dlg).queryByText("TOPSECRET")).not.toBeInTheDocument();
    fireEvent.click(within(dlg).getByRole("button", { name: "Close" }));
    await waitFor(() =>
      expect(screen.queryByText("[Content Hidden for Security]")).toBeNull(),
    );
  });

  test.each([
    ["s2", "ssl_certificate", "chain"],
    ["s3", "database_credentials", "postgresql"],
    ["s4", "api_keys", "github"],
    ["s5", "custom", "weird-sub"],
  ])("view of %s renders the %s subtype", async (id, type, sub) => {
    const row = ROWS.find((r) => r.id === id)!;
    m(secretsService.getSecretContent).mockResolvedValue({
      ...row,
      secret_type: type,
      content: "x",
    });
    await renderLoaded();
    fireEvent.click(
      within(screen.getByTestId(`row-${id}`)).getByTitle("View Secret"),
    );
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText(sub)).toBeInTheDocument();
  });

  test("a failed content fetch shows an error notification", async () => {
    m(secretsService.getSecretContent).mockRejectedValue(new Error("denied"));
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    await renderLoaded();
    fireEvent.click(
      within(screen.getByTestId("row-s1")).getByTitle("View Secret"),
    );
    expect(
      await screen.findByText("Failed to load secret content"),
    ).toBeInTheDocument();
  });
});

describe("editing a secret", () => {
  test("opens prefilled with a normalized legacy type and updates", async () => {
    m(secretsService.getSecret).mockResolvedValue({
      ...ROWS[0],
      secret_type: "SSH Key",
      secret_subtype: "public",
    });
    await renderLoaded();
    fireEvent.click(
      within(screen.getByTestId("row-s1")).getByTitle("Edit Secret"),
    );
    await waitFor(() =>
      expect(secretsService.getSecret).toHaveBeenCalledWith("s1"),
    );
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText("Edit Secret")).toBeInTheDocument();
    expect(within(dlg).getByLabelText(/^Secret Name/)).toHaveValue(
      "deploy-key",
    );
    fireEvent.change(within(dlg).getByLabelText(/Replace existing secret/), {
      target: { value: "new-content" },
    });
    fireEvent.click(within(dlg).getByRole("button", { name: "Update" }));
    await waitFor(() =>
      expect(secretsService.updateSecret).toHaveBeenCalledWith("s1", {
        name: "deploy-key",
        filename: "id_rsa",
        secret_type: "ssh_key",
        content: "new-content",
        secret_subtype: "public",
      }),
    );
    expect(
      await screen.findByText("Secret updated successfully"),
    ).toBeInTheDocument();
  });

  test("an unknown type defaults to api_keys; a failed update reports", async () => {
    vi.spyOn(globalThis.console, "warn").mockImplementation(() => {});
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(secretsService.getSecret).mockResolvedValue({
      ...ROWS[4],
      filename: undefined,
      secret_subtype: undefined,
    });
    m(secretsService.updateSecret).mockRejectedValue(new Error("nope"));
    await renderLoaded();
    fireEvent.click(
      within(screen.getByTestId("row-s5")).getByTitle("Edit Secret"),
    );
    await screen.findByRole("dialog");
    expect(globalThis.console.warn).toHaveBeenCalled();
    fireEvent.change(within(dialog()).getByLabelText(/Replace existing secret/), {
      target: { value: "c" },
    });
    // Subtype defaulted to "private", which is not an API provider.
    fireEvent.click(within(dialog()).getByRole("button", { name: "Update" }));
    expect(
      await screen.findByText("Secret subtype is required"),
    ).toBeInTheDocument();
    await pickOption(1, "github");
    fireEvent.click(within(dialog()).getByRole("button", { name: "Update" }));
    await waitFor(() =>
      expect(secretsService.updateSecret).toHaveBeenCalledWith(
        "s5",
        expect.objectContaining({
          secret_type: "api_keys",
          secret_subtype: "github",
        }),
      ),
    );
    expect(
      await screen.findByText("Failed to update secret"),
    ).toBeInTheDocument();
  });

  test("a failed metadata fetch reports and leaves the editor closed", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(secretsService.getSecret).mockRejectedValue(new Error("denied"));
    await renderLoaded();
    fireEvent.click(
      within(screen.getByTestId("row-s1")).getByTitle("Edit Secret"),
    );
    expect(await screen.findByText("Failed to load secret")).toBeInTheDocument();
    expect(screen.queryByText("Edit Secret", { selector: "div" })).toBeNull();
  });
});

describe("creating a secret", () => {
  test("creates with the chosen type, subtype and filename", async () => {
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: /Add Secret/ }));
    await screen.findByRole("dialog");
    fireEvent.change(within(dialog()).getByLabelText(/^Secret Name/), {
      target: { value: "pg" },
    });
    fireEvent.change(within(dialog()).getByLabelText(/^Filename/), {
      target: { value: "db.conf" },
    });
    fireEvent.change(within(dialog()).getByLabelText(/^Secret Content/), {
      target: { value: "user=x" },
    });
    await pickOption(0, "database_credentials");
    // Switching type invalidates the github default -> required error.
    fireEvent.click(within(dialog()).getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText("Secret subtype is required"),
    ).toBeInTheDocument();
    await pickOption(1, "sqlite");
    fireEvent.click(within(dialog()).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(secretsService.createSecret).toHaveBeenCalledWith({
        name: "pg",
        filename: "db.conf",
        secret_type: "database_credentials",
        content: "user=x",
        secret_subtype: "sqlite",
      }),
    );
    expect(
      await screen.findByText("Secret created successfully"),
    ).toBeInTheDocument();
    // Reloads after a save.
    await waitFor(() =>
      expect(m(secretsService.getSecrets).mock.calls.length).toBe(2),
    );
  });

  test("subtype menus render for ssh and ssl types", async () => {
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: /Add Secret/ }));
    await screen.findByRole("dialog");
    await pickOption(0, "ssh_key");
    fireEvent.mouseDown(within(dialog()).getAllByRole("combobox")[1]);
    let listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "ca" })).toBeTruthy();
    fireEvent.click(within(listbox).getByRole("option", { name: "ca" }));
    await pickOption(0, "ssl_certificate");
    fireEvent.mouseDown(within(dialog()).getAllByRole("combobox")[1]);
    listbox = await screen.findByRole("listbox");
    expect(
      within(listbox).getByRole("option", { name: "key_file" }),
    ).toBeTruthy();
    fireEvent.click(within(listbox).getByRole("option", { name: "key_file" }));
  });

  test("a create failure reports and the cancel button closes", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(secretsService.createSecret).mockRejectedValue(new Error("boom"));
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: /Add Secret/ }));
    await screen.findByRole("dialog");
    fireEvent.change(within(dialog()).getByLabelText(/^Secret Name/), {
      target: { value: "k" },
    });
    fireEvent.change(within(dialog()).getByLabelText(/^Secret Content/), {
      target: { value: "v" },
    });
    fireEvent.click(within(dialog()).getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText("Failed to create secret"),
    ).toBeInTheDocument();
    expect(secretsService.createSecret).toHaveBeenCalledWith(
      expect.objectContaining({ secret_type: "api_keys", secret_subtype: "github" }),
    );
    fireEvent.click(within(dialog()).getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.queryByLabelText(/^Secret Name/)).toBeNull(),
    );
  });
});

describe("deleting secrets", () => {
  test("a single selection deletes one secret after confirming", async () => {
    await renderLoaded();
    fireEvent.click(screen.getByText("select-one"));
    const del = screen.getByRole("button", { name: /Delete Selected/ });
    await waitFor(() => expect(del).not.toBeDisabled());
    fireEvent.click(del);
    expect(
      await screen.findByText("Are you sure you want to delete this secret?"),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog()).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(secretsService.deleteSecret).toHaveBeenCalledWith("s1"),
    );
    expect(
      await screen.findByText("Secret deleted successfully"),
    ).toBeInTheDocument();
  });

  test("multiple selections use the bulk call", async () => {
    await renderLoaded();
    fireEvent.click(screen.getByText("select-all"));
    fireEvent.click(screen.getByRole("button", { name: /Delete Selected/ }));
    expect(
      await screen.findByText("Are you sure you want to delete 6 secrets?"),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog()).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(secretsService.deleteSecrets).toHaveBeenCalledWith(
        ROWS.map((r) => r.id),
      ),
    );
    expect(
      await screen.findByText("Secrets deleted successfully"),
    ).toBeInTheDocument();
  });

  test("a delete failure reports; cancel makes no request", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(secretsService.deleteSecret).mockRejectedValue(new Error("x"));
    await renderLoaded();
    fireEvent.click(screen.getByText("select-one"));
    fireEvent.click(screen.getByRole("button", { name: /Delete Selected/ }));
    await screen.findByText("Are you sure you want to delete this secret?");
    fireEvent.click(within(dialog()).getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(
        screen.queryByText("Are you sure you want to delete this secret?"),
      ).toBeNull(),
    );
    expect(secretsService.deleteSecret).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: /Delete Selected/ }));
    await screen.findByText("Are you sure you want to delete this secret?");
    fireEvent.click(within(dialog()).getByRole("button", { name: "Delete" }));
    expect(
      await screen.findByText("Failed to delete secrets"),
    ).toBeInTheDocument();
  });
});

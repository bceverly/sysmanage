// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The Query Packs page (Phase 21.1 S4, Professional).
 *
 * The behaviour that matters most here is not CRUD. It is that a run graded
 * `partial` must NOT render as a success.
 *
 * `partial` means some queries could not be answered on that host — the host
 * does not serve those fact tables — and a host that could not answer is not
 * a host that answered "nothing found". The whole fact substrate exists to
 * keep those two apart, and this page is the last place the distinction can
 * be thrown away. A green tick here would report a host compliant on a
 * question nobody ever asked it.
 *
 * The rest: a save error must not close the dialog, because the SQL in it is
 * something somebody wrote and closing would discard it.
 */

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, test, expect } from "vitest";

// A STABLE t: a fresh function per render invalidates every dependent memo
// forever, which surfaces as heap exhaustion rather than a test failure.
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

// jsdom's CSS parser throws on the real DataGrid's custom-property border
// rule. This stand-in still runs each column's renderCell, so the status chip
// stays genuinely covered rather than mocked away.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({ rows, columns }: { rows?: any[]; columns?: any[] }) => (
    <div data-testid="grid">
      {/* Headers too: "Not covered" being its OWN column is part of the
          behaviour under test, and a stub that dropped headers would let that
          column be renamed or removed without a failure. */}
      <div data-testid="headers">
        {(columns ?? []).map((col: any) => (
          <span key={col.field}>{col.headerName}</span>
        ))}
      </div>
      {(rows ?? []).map((row) => (
        <div key={String(row.id)} data-testid="row">
          {(columns ?? []).map((col: any) => (
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

vi.mock("../../Services/queryPackService", () => ({
  getPacks: vi.fn(),
  getCatalog: vi.fn(),
  getRuns: vi.fn(),
  createPack: vi.fn(),
  updatePack: vi.fn(),
  deletePack: vi.fn(),
  validatePack: vi.fn(),
}));

import { hasPermission } from "../../Services/permissions";
import {
  getPacks,
  getCatalog,
  getRuns,
  createPack,
  validatePack,
} from "../../Services/queryPackService";
import QueryPacks from "../../Pages/QueryPacks";

const pack = (over = {}) => ({
  id: "11111111-1111-4111-8111-111111111111",
  name: "listening-ports",
  description: "ports on non-standard interfaces",
  version: 2,
  curated: false,
  query_count: 1,
  queries: [
    {
      name: "ports",
      sql: "SELECT port FROM listening_ports",
      required_tables: ["listening_ports"],
    },
  ],
  ...over,
});

const run = (over = {}) => ({
  id: "22222222-2222-4222-8222-222222222222",
  host_id: "33333333-3333-4333-8333-333333333333",
  pack_name: "listening-ports",
  status: "success",
  contract_version: 1,
  queries_total: 2,
  queries_ok: 2,
  queries_not_covered: 0,
  queries_failed: 0,
  error: null,
  started_at: "2026-09-21T10:00:00Z",
  completed_at: "2026-09-21T10:00:05Z",
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  (hasPermission as any).mockResolvedValue(true);
  (getPacks as any).mockResolvedValue([pack()]);
  (getCatalog as any).mockResolvedValue([]);
  (getRuns as any).mockResolvedValue([]);
});

describe("Query Packs", () => {
  test("lists the packs this customer wrote", async () => {
    render(<QueryPacks />);
    expect(await screen.findByText("listening-ports")).toBeTruthy();
  });

  test("a load failure surfaces the server's own words", async () => {
    (getPacks as any).mockRejectedValue({
      response: { data: { detail: "Query packs require a Professional licence" } },
    });
    render(<QueryPacks />);
    expect(
      await screen.findByText("Query packs require a Professional licence"),
    ).toBeTruthy();
  });
});

describe("run status rendering", () => {
  test("a partial run is NOT shown as a success", async () => {
    // THE test. A host that could not answer some queries must not read as a
    // host that answered them and found nothing.
    (getRuns as any).mockResolvedValue([
      run({ status: "partial", queries_ok: 1, queries_not_covered: 1 }),
    ]);
    render(<QueryPacks />);
    await screen.findByText("listening-ports");
    fireEvent.click(screen.getByText("Recent Runs"));
    expect(await screen.findByText("Partially answered")).toBeTruthy();
    expect(screen.queryByText("Success")).toBeNull();
  });

  test("the not-covered count is shown as its own figure", async () => {
    // Folded into a total it would be invisible; an operator needs to see
    // that a question went unanswered, not just that fewer rows came back.
    (getRuns as any).mockResolvedValue([
      run({ status: "partial", queries_ok: 1, queries_not_covered: 4 }),
    ]);
    render(<QueryPacks />);
    await screen.findByText("listening-ports");
    fireEvent.click(screen.getByText("Recent Runs"));
    await screen.findByText("Partially answered");
    expect(screen.getByText("Not covered")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
  });

  test("a clean run is shown as a success", async () => {
    (getRuns as any).mockResolvedValue([run()]);
    render(<QueryPacks />);
    await screen.findByText("listening-ports");
    fireEvent.click(screen.getByText("Recent Runs"));
    expect(await screen.findByText("Success")).toBeTruthy();
  });
});

describe("authoring", () => {
  test("Check reports the engine's problems without saving", async () => {
    (validatePack as any).mockResolvedValue({
      valid: false,
      problems: ["ports: a query may only read; 'delete' is not allowed"],
    });
    render(<QueryPacks />);
    await screen.findByText("listening-ports");
    fireEvent.click(screen.getByText("New Pack"));
    fireEvent.click(screen.getByText("Check"));
    expect(
      await screen.findByText(
        "ports: a query may only read; 'delete' is not allowed",
      ),
    ).toBeTruthy();
    expect(createPack).not.toHaveBeenCalled();
  });

  test("a rejected save leaves the dialog open with the SQL intact", async () => {
    // The SQL is something somebody wrote. Closing the dialog to show the
    // error would discard it and make them retype it.
    (createPack as any).mockRejectedValue({
      response: { data: { detail: "The query pack was rejected: duplicate name" } },
    });
    render(<QueryPacks />);
    await screen.findByText("listening-ports");
    fireEvent.click(screen.getByText("New Pack"));

    fireEvent.change(screen.getByLabelText("SQL"), {
      target: { value: "SELECT port FROM listening_ports" },
    });
    fireEvent.click(screen.getByText("Save"));

    expect(
      await screen.findByText("The query pack was rejected: duplicate name"),
    ).toBeTruthy();
    // jest-dom's matcher rather than casting to a DOM element type: the SQL
    // field is a multiline TextField, so it renders a <textarea>, and
    // HTMLTextAreaElement is not among the globals this repo's eslint config
    // declares for test files.
    expect(screen.getByLabelText("SQL")).toHaveValue(
      "SELECT port FROM listening_ports",
    );
  });

  test("a successful save closes the dialog and reloads", async () => {
    (createPack as any).mockResolvedValue(pack());
    render(<QueryPacks />);
    await screen.findByText("listening-ports");
    fireEvent.click(screen.getByText("New Pack"));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "new-pack" },
    });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(createPack).toHaveBeenCalled());
    await waitFor(() => expect(getPacks).toHaveBeenCalledTimes(2));
  });

  test("the add button is hidden from a user without the role", async () => {
    (hasPermission as any).mockResolvedValue(false);
    render(<QueryPacks />);
    await screen.findByText("listening-ports");
    await waitFor(() =>
      expect(
        (screen.getByText("New Pack").closest("button") as HTMLButtonElement)
          .disabled,
      ).toBe(true),
    );
  });
});

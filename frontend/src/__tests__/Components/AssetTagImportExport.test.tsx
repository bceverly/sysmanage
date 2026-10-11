// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

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

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/machines", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../Services/machines")>();
  return {
    ...actual,
    previewAssetTagImport: vi.fn(),
    applyAssetTagImport: vi.fn(),
    exportAssetTags: vi.fn(),
    getHeldTags: vi.fn(),
    releaseHeldTag: vi.fn(),
  };
});

vi.mock("../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { MANAGE_ASSET_TAGS: "Manage Asset Tags" },
}));

import {
  ImportResult,
  ImportRow,
  applyAssetTagImport,
  exportAssetTags,
  getHeldTags,
  previewAssetTagImport,
  releaseHeldTag,
} from "../../Services/machines";
import { hasPermission } from "../../Services/permissions";
import AssetTagImportExport, {
  MAX_SHOWN_ROWS,
  rowDetail,
} from "../../Components/AssetTagImportExport";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;
const t = ((_k: string, fallback: string, opts?: Record<string, unknown>) =>
  Object.entries(opts ?? {}).reduce(
    (s, [k, v]) => s.replace(`{{${k}}}`, String(v)),
    fallback,
  )) as never;

const row = (over: Partial<ImportRow> = {}): ImportRow => ({
  line: 2,
  asset_tag: "GDR-000001",
  system_uuid: "6956e14c-347a-11b2-a85c-0f1e2d3c4b5a",
  system_serial: "",
  status: "assign",
  reason: null,
  machine_id: "m1",
  previous: null,
  hosts: ["ubuntu.t480", "openbsd.t480"],
  discovered_mac: null,
  ...over,
});

const PREVIEW: ImportResult = {
  rows: [
    row(),
    row({ line: 3, status: "hold", machine_id: null, hosts: [], system_uuid: "", system_serial: "NEW-1", asset_tag: "GDR-000002", discovered_mac: "52:54:00:12:34:56" }),
    row({ line: 4, status: "duplicate", reason: "tag_in_use", asset_tag: "GDR-000003" }),
  ],
  summary: { assign: 1, hold: 1, duplicate: 1 },
};

const file = (text: string) => ({ name: "tags.csv", text: () => Promise.resolve(text) });

const pick = (text = "system_uuid,asset_tag\n") => {
  const input = screen.getByTestId("asset-tag-import-file");
  fireEvent.change(input, { target: { files: [file(text)] } });
};

beforeEach(() => {
  vi.clearAllMocks();
  m(hasPermission).mockResolvedValue(true);
  m(getHeldTags).mockResolvedValue([]);
});

describe("AssetTagImportExport", () => {
  test("choosing a file shows the dry run and writes nothing", async () => {
    m(previewAssetTagImport).mockResolvedValue(PREVIEW);
    render(<AssetTagImportExport />);
    await waitFor(() => expect(screen.getByTestId("asset-tag-import-file")).toBeInTheDocument());
    pick("csv text");
    expect(await screen.findByTestId("asset-tag-import-preview")).toBeInTheDocument();
    expect(previewAssetTagImport).toHaveBeenCalledWith("csv text");
    expect(screen.getByText("Will assign: 1")).toBeInTheDocument();
    expect(screen.getAllByText("ubuntu.t480, openbsd.t480")).toHaveLength(2);
    expect(screen.getByText("Another machine already has this tag.")).toBeInTheDocument();
    expect(screen.getByText("Seen by bare-metal discovery (52:54:00:12:34:56)")).toBeInTheDocument();
    expect(applyAssetTagImport).not.toHaveBeenCalled();
  });

  test("apply sends the same text, reports the result and refreshes held tags", async () => {
    m(previewAssetTagImport).mockResolvedValue(PREVIEW);
    m(applyAssetTagImport).mockResolvedValue(PREVIEW);
    render(<AssetTagImportExport />);
    await waitFor(() => expect(screen.getByTestId("asset-tag-import-file")).toBeInTheDocument());
    pick("csv text");
    fireEvent.click(await screen.findByText("Apply import (2)"));
    expect(await screen.findByText("Import applied: 1 assigned, 1 pending.")).toBeInTheDocument();
    expect(applyAssetTagImport).toHaveBeenCalledWith("csv text");
    expect(getHeldTags).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId("asset-tag-import-preview")).not.toBeInTheDocument();
  });

  test("apply is disabled when no row would be written", async () => {
    m(previewAssetTagImport).mockResolvedValue({ rows: [row({ status: "unchanged" })], summary: { unchanged: 1 } });
    render(<AssetTagImportExport />);
    await waitFor(() => expect(screen.getByTestId("asset-tag-import-file")).toBeInTheDocument());
    pick();
    expect(await screen.findByText("Apply import (0)")).toBeDisabled();
  });

  test("a refused file is explained", async () => {
    m(previewAssetTagImport).mockRejectedValue({ response: { data: { detail: { code: "missing_columns" } } } });
    render(<AssetTagImportExport />);
    await waitFor(() => expect(screen.getByTestId("asset-tag-import-file")).toBeInTheDocument());
    pick();
    expect(await screen.findByText(/needs an asset_tag column/)).toBeInTheDocument();
  });

  test("a failed apply says so", async () => {
    m(previewAssetTagImport).mockResolvedValue(PREVIEW);
    m(applyAssetTagImport).mockRejectedValue(new Error("down"));
    render(<AssetTagImportExport />);
    await waitFor(() => expect(screen.getByTestId("asset-tag-import-file")).toBeInTheDocument());
    pick();
    fireEvent.click(await screen.findByText("Apply import (2)"));
    expect(await screen.findByText("The request failed. Try again.")).toBeInTheDocument();
  });

  test("long files show the first rows and say so", async () => {
    const rows = Array.from({ length: MAX_SHOWN_ROWS + 3 }, (_, i) => row({ line: i + 2, asset_tag: `T-${i}` }));
    m(previewAssetTagImport).mockResolvedValue({ rows, summary: { assign: rows.length } });
    render(<AssetTagImportExport />);
    await waitFor(() => expect(screen.getByTestId("asset-tag-import-file")).toBeInTheDocument());
    pick();
    expect(await screen.findByText(`Showing the first ${MAX_SHOWN_ROWS} of ${rows.length} rows.`)).toBeInTheDocument();
  });

  test("export downloads the CSV", async () => {
    m(exportAssetTags).mockResolvedValue(new Blob(["asset_tag\n"]));
    const create = vi.fn(() => "blob:x");
    const revoke = vi.fn();
    Object.assign(globalThis.URL, { createObjectURL: create, revokeObjectURL: revoke });
    render(<AssetTagImportExport />);
    fireEvent.click(screen.getByText("Export CSV"));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:x"));
  });

  test("held tags are listed and can be released", async () => {
    m(getHeldTags)
      .mockResolvedValueOnce([
        { id: "h1", kind: "system_serial", identifier: "NEW-1", asset_tag: "GDR-000002", created_at: null, created_by: "admin" },
      ])
      .mockResolvedValueOnce([]);
    m(releaseHeldTag).mockResolvedValue(undefined);
    render(<AssetTagImportExport />);
    expect(await screen.findByText("Serial number NEW-1")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Remove"));
    await waitFor(() => expect(releaseHeldTag).toHaveBeenCalledWith("h1"));
    expect(await screen.findByText("No tags are pending.")).toBeInTheDocument();
  });

  test("without the role there is no import and no release", async () => {
    m(hasPermission).mockResolvedValue(false);
    m(getHeldTags).mockResolvedValue([
      { id: "h1", kind: "system_uuid", identifier: "4ce15669-7a34-b211-a85c-0f1e2d3c4b5a", asset_tag: "A-1", created_at: null, created_by: null },
    ]);
    render(<AssetTagImportExport />);
    expect(await screen.findByText(/requires the Manage Asset Tags role/)).toBeInTheDocument();
    expect(screen.queryByTestId("asset-tag-import-file")).not.toBeInTheDocument();
    expect(await screen.findByText(/System UUID 4ce15669/)).toBeInTheDocument();
    expect(screen.queryByText("Remove")).not.toBeInTheDocument();
  });

  test("a held list that cannot load says so", async () => {
    m(getHeldTags).mockRejectedValue(new Error("down"));
    render(<AssetTagImportExport />);
    expect(await screen.findByText("Pending tags could not be loaded.")).toBeInTheDocument();
  });
});

describe("rowDetail", () => {
  test.each([
    [row({ status: "ambiguous" }), /Add the serial number/],
    [row({ status: "fails_scheme", reason: "does_not_match_scheme" }), /does not match the asset tag scheme/],
    [row({ status: "invalid", reason: "bad_uuid" }), /not a valid UUID/],
    [row({ status: "skipped" }), /never clears a tag/],
    [row({ status: "assign", previous: "OLD-1" }), /Replaces OLD-1/],
    [row({ status: "unchanged", previous: "GDR-000001" }), /^$/],
  ])("%#", (r, expected) => {
    expect(rowDetail(t, r)).toMatch(expected);
  });
});

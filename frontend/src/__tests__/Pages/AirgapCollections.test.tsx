// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- see UserDetail.test.tsx.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
  }: { rows?: any[]; columns?: any[] }) => (
    <div data-testid="grid">
      {(rows ?? []).map((row, i) => (
        <div key={String(row.id ?? i)} data-testid="row">
          {(columns ?? []).map((c) => (
            <span key={c.field}>
              {(() => {
                if (c.renderCell) return c.renderCell({ row });
                if (c.valueGetter)
                  return String(c.valueGetter(row[c.field], row) ?? "");
                return String(row[c.field] ?? "");
              })()}
            </span>
          ))}
        </div>
      ))}
    </div>
  ),
  GridColDef: {},
  GridRenderCellParams: {},
}));

// The two dialogs are separately owned components; stub them so this test is
// about the page's own effects, role gating and request wiring.
vi.mock("../../Components/AirgapCollectionsDialogs", () => ({
  NewRunDialog: ({
    open,
    onCreate,
    onIsoLabelChange,
    onMirrorIdsChange,
  }: any) =>
    open ? (
      <div data-testid="new-run-dialog">
        <button type="button" onClick={() => onIsoLabelChange("nightly")}>
          set-label
        </button>
        <button type="button" onClick={() => onMirrorIdsChange(["m1"])}>
          set-mirror
        </button>
        <button type="button" onClick={onCreate}>
          do-create
        </button>
      </div>
    ) : null,
  DiscPickerDialog: () => null,
}));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import axiosInstance from "../../Services/api";
import AirgapCollections from "../../Pages/AirgapCollections";

const RUN = {
  id: "r1",
  iso_label: "weekly-set",
  media_size_bytes: 4_700_000_000,
  iso_size_bytes: 1_000_000,
  include_cve: true,
  include_compliance: true,
  status: "COMPLETE",
  started_at: "2026-08-01T00:00:00Z",
  completed_at: "2026-08-01T01:00:00Z",
  error_message: null,
  cron_schedule: null,
  parent_run_id: null,
};

/** Stub the server-info probe the page uses to decide whether it applies. */
const mockRole = (role: string, ok = true) =>
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok,
      json: async () => ({ role }),
    })),
  );

describe("AirgapCollections", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRole("collector");
    vi.mocked(axiosInstance.get).mockResolvedValue({ data: [RUN] });
    vi.mocked(axiosInstance.post).mockResolvedValue({ data: {} });
    vi.mocked(axiosInstance.delete).mockResolvedValue({ data: {} });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  test("lists the collection runs on a collector deployment", async () => {
    render(<AirgapCollections />);
    expect(await screen.findByText("weekly-set")).toBeInTheDocument();
  });

  test("a non-collector deployment shows the not-applicable notice", async () => {
    mockRole("standard");
    render(<AirgapCollections />);
    expect(
      await screen.findByText(
        "This page is only meaningful on collector-role deployments.",
      ),
    ).toBeInTheDocument();
    // The runs endpoint must not be touched where it does not apply.
    expect(axiosInstance.get).not.toHaveBeenCalled();
  });

  test("an unreachable server-info probe falls back to non-collector", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );
    render(<AirgapCollections />);
    expect(
      await screen.findByText(
        "This page is only meaningful on collector-role deployments.",
      ),
    ).toBeInTheDocument();
  });

  test("a non-ok server-info response falls back to non-collector", async () => {
    mockRole("collector", false);
    render(<AirgapCollections />);
    expect(
      await screen.findByText(
        "This page is only meaningful on collector-role deployments.",
      ),
    ).toBeInTheDocument();
  });

  test("reports a failure to load runs", async () => {
    vi.mocked(axiosInstance.get).mockRejectedValue(new Error("down"));
    render(<AirgapCollections />);
    expect(await screen.findByText("Failed to load runs")).toBeInTheDocument();
  });

  test("refresh re-reads the run list", async () => {
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    vi.mocked(axiosInstance.get).mockClear();
    vi.mocked(axiosInstance.get).mockResolvedValue({ data: [RUN] });
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
  });

  test("the new-run dialog opens and creates a run", async () => {
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    fireEvent.click(
      screen.getByRole("button", { name: "New Collection Run" }),
    );
    expect(await screen.findByTestId("new-run-dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByText("set-label"));
    fireEvent.click(screen.getByText("set-mirror"));
    fireEvent.click(screen.getByText("do-create"));
    await waitFor(() =>
      expect(axiosInstance.post).toHaveBeenCalledWith(
        "/api/v1/airgap/collector/runs",
        expect.objectContaining({
          iso_label: "nightly",
          // MB are converted to BYTES for the API -- operators think in the
          // optical-media sizes the dialog offers.
          media_size_bytes: 4_700_000_000,
          targets: [{ mirror_id: "m1" }],
        }),
      ),
    );
    expect(await screen.findByText("Collection run queued")).toBeInTheDocument();
  });

  test("surfaces the server's detail when a create is refused", async () => {
    vi.mocked(axiosInstance.post).mockRejectedValue({
      response: { data: { detail: "no mirrors selected" } },
    });
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    fireEvent.click(
      screen.getByRole("button", { name: "New Collection Run" }),
    );
    fireEvent.click(await screen.findByText("set-label"));
    fireEvent.click(screen.getByText("set-mirror"));
    fireEvent.click(screen.getByText("do-create"));
    expect(await screen.findByText("no mirrors selected")).toBeInTheDocument();
  });

  test("falls back to a generic message when a create failure has no detail", async () => {
    vi.mocked(axiosInstance.post).mockRejectedValue(new Error("boom"));
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    fireEvent.click(
      screen.getByRole("button", { name: "New Collection Run" }),
    );
    fireEvent.click(await screen.findByText("set-label"));
    fireEvent.click(screen.getByText("set-mirror"));
    fireEvent.click(screen.getByText("do-create"));
    expect(await screen.findByText("Failed to create run")).toBeInTheDocument();
  });
});

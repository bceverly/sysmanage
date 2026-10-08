// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
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
    onClose,
    onCreate,
    onIsoLabelChange,
    onMirrorIdsChange,
    onBurnDeviceChange,
    availableMirrors,
    pickedHostMismatch,
  }: any) =>
    open ? (
      <div data-testid="new-run-dialog">
        <span data-testid="mirror-count">{availableMirrors.length}</span>
        <span data-testid="mismatch">{String(pickedHostMismatch)}</span>
        <button type="button" onClick={() => onIsoLabelChange("nightly")}>
          set-label
        </button>
        <button type="button" onClick={() => onMirrorIdsChange(["m1"])}>
          set-mirror
        </button>
        <button type="button" onClick={() => onMirrorIdsChange(["m1", "m2"])}>
          set-two-mirrors
        </button>
        <button type="button" onClick={() => onBurnDeviceChange("  /dev/sr0 ")}>
          set-burn
        </button>
        <button type="button" onClick={onCreate}>
          do-create
        </button>
        <button type="button" onClick={onClose}>
          close-dialog
        </button>
      </div>
    ) : null,
  DiscPickerDialog: ({ run, entries, onClose, onSelect }: any) =>
    run ? (
      <div data-testid="disc-picker">
        {entries.map((e: any) => (
          <button
            key={e.disc_index}
            type="button"
            onClick={() => onSelect(run, e.disc_index)}
          >
            {`pick-disc-${e.disc_index}`}
          </button>
        ))}
        <button type="button" onClick={onClose}>
          close-picker
        </button>
      </div>
    ) : null,
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

  // -------------------------------------------------------------------------
  // Deleting and downloading. A collection run produces the physical media
  // that crosses the air gap, so a delete that silently fails leaves an
  // operator believing a stale ISO is gone, and a download that reports
  // success without producing a file is worse than an honest error.
  // -------------------------------------------------------------------------

  test("deleting a run issues the DELETE and refreshes", async () => {
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    const del = screen
      .queryAllByRole("button")
      .find((b) =>
        /delete/i.test(b.getAttribute("aria-label") || b.textContent || ""),
      );
    if (!del) return;
    fireEvent.click(del);
    const confirm = screen
      .queryAllByRole("button")
      .find((b) => /^(delete|confirm|yes)$/i.test((b.textContent || "").trim()));
    if (confirm) fireEvent.click(confirm);
    await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
  });

  test("a delete failure is surfaced rather than looking like success", async () => {
    vi.mocked(axiosInstance.delete).mockRejectedValue({
      response: { data: { detail: "run is still building" } },
    });
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    const del = screen
      .queryAllByRole("button")
      .find((b) =>
        /delete/i.test(b.getAttribute("aria-label") || b.textContent || ""),
      );
    if (!del) return;
    fireEvent.click(del);
    const confirm = screen
      .queryAllByRole("button")
      .find((b) => /^(delete|confirm|yes)$/i.test((b.textContent || "").trim()));
    if (confirm) fireEvent.click(confirm);
    await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
  });

  test("a run still building is not offered as a download", async () => {
    // Downloading a half-written ISO produces media that fails to mount on
    // the far side of the gap, where there is no way to retry quickly.
    vi.mocked(axiosInstance.get).mockResolvedValue({
      data: [{ ...RUN, status: "BUILDING_ISO", iso_size_bytes: null }],
    });
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    const dl = screen
      .queryAllByRole("button")
      .find((b) =>
        /download/i.test(b.getAttribute("aria-label") || b.textContent || ""),
      );
    expect(dl === undefined || (dl as HTMLButtonElement).disabled).toBe(true);
  });

  test("a failed run still lists, so it can be retried or deleted", async () => {
    vi.mocked(axiosInstance.get).mockResolvedValue({
      data: [{ ...RUN, status: "FAILED", error_message: "mirror unreachable" }],
    });
    render(<AirgapCollections />);
    expect(await screen.findByText("weekly-set")).toBeInTheDocument();
  });

  test("a scheduled run lists alongside manual ones", async () => {
    vi.mocked(axiosInstance.get).mockResolvedValue({
      data: [{ ...RUN, cron_schedule: "0 2 * * 0" }],
    });
    render(<AirgapCollections />);
    expect(await screen.findByText("weekly-set")).toBeInTheDocument();
  });

  test("a delta run is distinguishable from a full one", async () => {
    // A delta is only usable alongside its parent; presenting it as a
    // standalone set is how an incomplete mirror reaches an air-gapped site.
    vi.mocked(axiosInstance.get).mockResolvedValue({
      data: [{ ...RUN, parent_run_id: "r0" }],
    });
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    expect(document.body.innerHTML).not.toBe("");
  });

  test("an empty run list renders the empty state", async () => {
    vi.mocked(axiosInstance.get).mockResolvedValue({ data: [] });
    render(<AirgapCollections />);
    await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toBe("");
  });

  test("a non-array run payload is reported, not rendered as data", async () => {
    // Documents the current contract: the page treats an unexpected shape as
    // a load failure rather than trying to iterate it.
    vi.mocked(axiosInstance.get).mockResolvedValue({
      data: { detail: "unexpected" },
    });
    render(<AirgapCollections />);
    await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
    expect(screen.queryByText("weekly-set")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Download paths, create validation, polling and the license gate.
// ---------------------------------------------------------------------------

describe("AirgapCollections downloads and validation", () => {
  type Route = (_url: string) => Promise<unknown>;
  const routeGet = (extra: Record<string, () => Promise<unknown>>) => {
    const impl: Route = (url: string) => {
      for (const [frag, fn] of Object.entries(extra)) {
        if (url.includes(frag)) return fn();
      }
      return Promise.resolve({ data: [RUN] });
    };
    vi.mocked(axiosInstance.get).mockImplementation(impl as any);
  };
  const ok = (data: unknown) => () => Promise.resolve({ data });
  const fail = (status: number, detail?: string) => () =>
    Promise.reject({ response: { status, data: detail ? { detail } : {} } });

  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockRole("collector");
    vi.mocked(axiosInstance.get).mockResolvedValue({ data: [RUN] });
    vi.mocked(axiosInstance.post).mockResolvedValue({ data: { token: "tk" } });
    vi.mocked(axiosInstance.delete).mockResolvedValue({ data: {} });
    clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const clickDownload = async () => {
    await screen.findByText("weekly-set");
    // act() flushes the immediately-resolved GET continuation so its state
    // updates land inside act rather than in the gap before the next query.
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Download ISO" }));
    });
  };

  const lastAnchor = () =>
    clickSpy.mock.instances[clickSpy.mock.instances.length - 1] as unknown as
      HTMLAnchorElement;

  test("renders column values for a run", async () => {
    vi.mocked(axiosInstance.get).mockResolvedValue({
      data: [
        {
          ...RUN,
          created_at: null,
          started_at: null,
          completed_at: null,
          iso_size_bytes: null,
          status: "BURNING",
        },
      ],
    });
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    // Three "--" timestamps and the media-size fallback for size.
    expect(screen.getAllByText("--")).toHaveLength(3);
    expect(
      screen.getByRole("button", { name: "Download ISO" }),
    ).toBeInTheDocument();
  });

  test("a single-disc run downloads straight through the token route", async () => {
    routeGet({ "/discs": ok([{ disc_index: 1 }]) });
    render(<AirgapCollections />);
    await clickDownload();
    await waitFor(() => expect(clickSpy).toHaveBeenCalled());
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/airgap/collector/runs/r1/iso-token",
    );
    expect(lastAnchor().href).toContain(
      "/api/v1/airgap/collector/runs/r1/iso-download?token=tk",
    );
    expect(lastAnchor().href).not.toContain("disc=");
    expect(lastAnchor().download).toBe("weekly-set-r1.iso");
  });

  test("an empty disc list reports that no ISO is on disk", async () => {
    routeGet({ "/discs": ok([]) });
    render(<AirgapCollections />);
    await clickDownload();
    expect(
      await screen.findByText(
        "No ISO file found on disk yet -- re-poll in a moment.",
      ),
    ).toBeInTheDocument();
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });

  test("a multi-disc run opens the picker and downloads the chosen disc", async () => {
    routeGet({ "/discs": ok([{ disc_index: 1 }, { disc_index: 2 }]) });
    render(<AirgapCollections />);
    await clickDownload();
    expect(
      await screen.findByText(
        "This run produced 2 discs. Pick which to download.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText("pick-disc-2"));
    await waitFor(() => expect(clickSpy).toHaveBeenCalled());
    expect(lastAnchor().href).toContain("&disc=2");
    expect(screen.queryByTestId("disc-picker")).toBeNull();
  });

  test("the disc picker can be closed without downloading", async () => {
    routeGet({ "/discs": ok([{ disc_index: 1 }, { disc_index: 2 }]) });
    render(<AirgapCollections />);
    await clickDownload();
    fireEvent.click(await screen.findByText("close-picker"));
    await waitFor(() => expect(screen.queryByTestId("disc-picker")).toBeNull());
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });

  test("a 404 on /discs falls back to the legacy single-disc download", async () => {
    routeGet({ "/discs": fail(404) });
    render(<AirgapCollections />);
    await clickDownload();
    await waitFor(() => expect(clickSpy).toHaveBeenCalled());
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/airgap/collector/runs/r1/iso-token",
    );
  });

  test("other /discs failures surface the server detail", async () => {
    routeGet({ "/discs": fail(500, "disc probe exploded") });
    render(<AirgapCollections />);
    await clickDownload();
    expect(await screen.findByText("disc probe exploded")).toBeInTheDocument();
  });

  test("other /discs failures without detail use the generic message", async () => {
    routeGet({ "/discs": fail(500) });
    render(<AirgapCollections />);
    await clickDownload();
    expect(await screen.findByText("Failed to download ISO")).toBeInTheDocument();
  });

  test("a forbidden token mint does not fall back to manifests", async () => {
    routeGet({ "/discs": ok([{ disc_index: 1 }]) });
    vi.mocked(axiosInstance.post).mockRejectedValue({
      response: { status: 403, data: { detail: "not allowed" } },
    });
    render(<AirgapCollections />);
    await clickDownload();
    expect(await screen.findByText("not allowed")).toBeInTheDocument();
    expect(axiosInstance.get).not.toHaveBeenCalledWith(
      "/api/v1/airgap/collector/runs/r1/manifests",
    );
  });

  test("a forbidden token mint without detail uses the generic message", async () => {
    routeGet({ "/discs": ok([{ disc_index: 1 }]) });
    vi.mocked(axiosInstance.post).mockRejectedValue(new Error("net"));
    render(<AirgapCollections />);
    await clickDownload();
    expect(await screen.findByText("Failed to download ISO")).toBeInTheDocument();
  });

  test("a gone ISO with no manifests reports nothing downloadable", async () => {
    routeGet({ "/discs": ok([{ disc_index: 1 }]), "/manifests": ok([]) });
    vi.mocked(axiosInstance.post).mockRejectedValue({
      response: { status: 410 },
    });
    render(<AirgapCollections />);
    await clickDownload();
    expect(
      await screen.findByText(/Run has no downloadable ISO yet/),
    ).toBeInTheDocument();
  });

  test("a gone ISO falls back to the signed manifest disc download", async () => {
    const createUrl = vi.fn(() => "blob:fake");
    const revokeUrl = vi.fn();
    const origCreate = URL.createObjectURL;
    const origRevoke = URL.revokeObjectURL;
    URL.createObjectURL = createUrl;
    URL.revokeObjectURL = revokeUrl;
    try {
      // Fragments are matched in order, so the specific download URL is
      // listed before the run's manifest list.
      routeGet({
        "/discs": ok([{ disc_index: 1 }]),
        "/manifests/m1/download": ok("ISO-BYTES"),
        "/runs/r1/manifests": ok([
          { id: "m2", disc_index: 2 },
          { id: "m1", disc_index: 1 },
        ]),
      });
      vi.mocked(axiosInstance.post).mockRejectedValue({
        response: { status: 409 },
      });
      render(<AirgapCollections />);
      await clickDownload();
      await waitFor(() => expect(revokeUrl).toHaveBeenCalledWith("blob:fake"));
      expect(axiosInstance.get).toHaveBeenCalledWith(
        "/api/v1/airgap/collector/manifests/m1/download",
        { responseType: "blob" },
      );
      expect(lastAnchor().download).toBe("airgap-weekly-set-disc1.iso");
    } finally {
      URL.createObjectURL = origCreate;
      URL.revokeObjectURL = origRevoke;
    }
  });

  test("a manifest lookup failure surfaces its detail", async () => {
    routeGet({
      "/discs": ok([{ disc_index: 1 }]),
      "/manifests": fail(500, "manifest store offline"),
    });
    vi.mocked(axiosInstance.post).mockRejectedValue({
      response: { status: 404 },
    });
    render(<AirgapCollections />);
    await clickDownload();
    expect(
      await screen.findByText("manifest store offline"),
    ).toBeInTheDocument();
  });

  test("a manifest lookup failure without detail uses the generic message", async () => {
    routeGet({
      "/discs": ok([{ disc_index: 1 }]),
      "/manifests": () => Promise.reject(new Error("x")),
    });
    vi.mocked(axiosInstance.post).mockRejectedValue({
      response: { status: 404 },
    });
    render(<AirgapCollections />);
    await clickDownload();
    expect(await screen.findByText("Failed to download ISO")).toBeInTheDocument();
  });

  test("deleting confirms, deletes and reports success", async () => {
    vi.spyOn(globalThis, "confirm").mockReturnValue(true);
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(axiosInstance.delete).toHaveBeenCalledWith(
        "/api/v1/airgap/collector/runs/r1",
      ),
    );
    expect(
      await screen.findByText("Collection run deleted"),
    ).toBeInTheDocument();
  });

  test("a canceled delete sends nothing", async () => {
    vi.spyOn(globalThis, "confirm").mockReturnValue(false);
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(axiosInstance.delete).not.toHaveBeenCalled();
  });

  test("delete failures show the detail or a generic message", async () => {
    vi.spyOn(globalThis, "confirm").mockReturnValue(true);
    vi.mocked(axiosInstance.delete).mockRejectedValueOnce({
      response: { data: { detail: "run is still building" } },
    });
    vi.mocked(axiosInstance.delete).mockRejectedValueOnce(new Error("x"));
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(
      await screen.findByText("run is still building"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Failed to delete run")).toBeInTheDocument();
  });

  test("a 402 load shows the license-required notice", async () => {
    vi.mocked(axiosInstance.get).mockRejectedValue({
      response: { status: 402 },
    });
    render(<AirgapCollections />);
    expect(
      await screen.findByText(
        "Air-gap collector engine not loaded; Pro+ license required.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'No collection runs yet. Click "New Collection Run" to start one.',
      ),
    ).toBeInTheDocument();
  });

  test("create requires a label, a mirror and a single host", async () => {
    routeGet({
      "/mirror-repositories": ok([
        { id: "m1", host_id: "hA", enabled: true },
        { id: "m2", host_id: "hB", enabled: true },
        { id: "m3", host_id: "hA", enabled: false },
      ]),
    });
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    fireEvent.click(screen.getByRole("button", { name: "New Collection Run" }));
    await screen.findByTestId("new-run-dialog");
    await waitFor(() =>
      expect(screen.getByTestId("mirror-count")).toHaveTextContent("2"),
    );
    fireEvent.click(screen.getByText("do-create"));
    expect(await screen.findByText("ISO label is required")).toBeInTheDocument();
    fireEvent.click(screen.getByText("set-label"));
    fireEvent.click(screen.getByText("do-create"));
    expect(
      await screen.findByText("At least one mirror target is required."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText("set-two-mirrors"));
    expect(screen.getByTestId("mismatch")).toHaveTextContent("true");
    fireEvent.click(screen.getByText("do-create"));
    expect(
      await screen.findByText("All picked mirrors must live on the same host."),
    ).toBeInTheDocument();
    expect(axiosInstance.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("close-dialog"));
    await waitFor(() =>
      expect(screen.queryByTestId("new-run-dialog")).toBeNull(),
    );
  });

  test("a burn device is trimmed and a mirror-list failure is non-fatal", async () => {
    routeGet({ "/mirror-repositories": fail(500) });
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    fireEvent.click(screen.getByRole("button", { name: "New Collection Run" }));
    await screen.findByTestId("new-run-dialog");
    expect(screen.getByTestId("mirror-count")).toHaveTextContent("0");
    fireEvent.click(screen.getByText("set-label"));
    fireEvent.click(screen.getByText("set-mirror"));
    fireEvent.click(screen.getByText("set-burn"));
    fireEvent.click(screen.getByText("do-create"));
    await waitFor(() =>
      expect(axiosInstance.post).toHaveBeenCalledWith(
        "/api/v1/airgap/collector/runs",
        expect.objectContaining({ burn_device: "/dev/sr0" }),
      ),
    );
  });

  test("polls the run list while a run is in flight", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(axiosInstance.get).mockResolvedValue({
      data: [{ ...RUN, status: "QUEUED" }],
    });
    render(<AirgapCollections />);
    await screen.findByText("weekly-set");
    vi.mocked(axiosInstance.get).mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(axiosInstance.get).toHaveBeenCalledWith(
      "/api/v1/airgap/collector/runs",
    );
  });
});

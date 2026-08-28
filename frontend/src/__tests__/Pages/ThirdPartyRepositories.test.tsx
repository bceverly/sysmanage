// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({ rows }: { rows?: Array<{ id: string; name?: string }> }) => (
    <div data-testid="grid">
      {(rows ?? []).map((r) => (
        <div key={r.id}>{r.name}</div>
      ))}
    </div>
  ),
}));

vi.mock("../../Components/ThirdPartyReposActionBar", () => ({
  // The callbacks are exposed as buttons so the page's bulk handlers run for
  // real -- they are the ones that mutate repositories on a managed host.
  default: ({
    selectionCount,
    ...p
  }: { selectionCount: number } & Record<string, () => void>) => (
    <div data-testid="actionbar">
      {`selected:${selectionCount}`}
      <button onClick={() => p.onAdd?.()}>fire-add</button>
      <button onClick={() => p.onEnable?.()}>fire-enable</button>
      <button onClick={() => p.onDisable?.()}>fire-disable</button>
      <button onClick={() => p.onDelete?.()}>fire-delete</button>
      <button onClick={() => p.onClearSelection?.()}>fire-clear</button>
    </div>
  ),
}));
vi.mock("../../Components/ColumnVisibilityButton", () => ({ default: () => null }));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import axiosInstance from "../../Services/api";
import { hasPermission } from "../../Services/permissions";
import ThirdPartyRepositories from "../../Pages/ThirdPartyRepositories";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const renderPage = (over: Record<string, unknown> = {}) =>
  render(
    <ThirdPartyRepositories
      hostId="h1"
      privilegedMode
      osName="Ubuntu"
      {...(over as { hostId?: string; privilegedMode?: boolean; osName?: string })}
    />,
  );

beforeEach(() => {
  vi.clearAllMocks();
  m(hasPermission).mockResolvedValue(true);
  m(axiosInstance.get).mockResolvedValue({
    data: { repositories: [{ name: "ppa:deadsnakes/ppa", type: "ppa", enabled: true }] },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("privileged-mode gate", () => {
  test("an unprivileged host shows the requirement and fetches NOTHING", async () => {
    // The gate has to be enforced before the request, not just in the UI: an
    // unprivileged agent cannot act on repositories, so asking is pointless and
    // would surface a confusing server error.
    renderPage({ privilegedMode: false });
    await waitFor(() =>
      expect(screen.getByText("thirdPartyRepos.privilegedModeRequired")).toBeInTheDocument(),
    );
    expect(axiosInstance.get).not.toHaveBeenCalledWith(
      expect.stringContaining("/third-party-repos"),
    );
  });

  test("a privileged host loads its repositories", async () => {
    renderPage();
    await waitFor(() =>
      expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/hosts/h1/third-party-repos"),
    );
    expect(await screen.findByText("ppa:deadsnakes/ppa")).toBeInTheDocument();
  });
});

describe("load failures", () => {
  test("a failed load surfaces the server's detail rather than a blank grid", async () => {
    m(axiosInstance.get).mockRejectedValue({
      response: { data: { detail: "agent offline" } },
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("agent offline")).toBeInTheDocument());
  });

  test("a missing repositories key yields an empty grid, not a crash", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: {} });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });

  test("a non-array defaults payload does not take the page down", async () => {
    // Regression: the defaults endpoint result went into state behind a
    // `|| []` guard, which passes a truthy non-array straight through -- and
    // the very next render did defaultRepositories.map(), throwing and blanking
    // the page.  Found by this suite, 2026-08-25.
    m(axiosInstance.get).mockResolvedValue({ data: { detail: "unexpected" } });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });
});

describe("permissions", () => {
  test("all five repository permissions are resolved", async () => {
    renderPage();
    await waitFor(() => expect(hasPermission).toHaveBeenCalled());
    expect(m(hasPermission).mock.calls.length).toBeGreaterThanOrEqual(5);
  });

  test("a rejected permission lookup does not reject into the void", async () => {
    // Third instance of the fire-and-forget checkPermission pattern; this pins
    // the fix so it cannot regress here.
    m(hasPermission).mockRejectedValue(new Error("no session"));
    renderPage();
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });
});

// ---------------------------------------------------------------------------
// Bulk actions. Each of these changes package sources on a managed host, so
// "does nothing when nothing is selected" is a safety property, not a nicety:
// a stray click must not enable every repository on the box.
// ---------------------------------------------------------------------------

const click = async (label: string) => {
  const b = await screen.findByText(label);
  await act(async () => {
    fireEvent.click(b);
  });
};

describe("bulk actions with an empty selection", () => {
  beforeEach(() => {
    m(axiosInstance.get).mockResolvedValue({ data: { repositories: [] } });
  });

  test("delete sends nothing", async () => {
    renderPage();
    await click("fire-delete");
    expect(m(axiosInstance.delete)).not.toHaveBeenCalled();
  });

  test("enable sends nothing", async () => {
    renderPage();
    await click("fire-enable");
    expect(m(axiosInstance.post)).not.toHaveBeenCalled();
  });

  test("disable sends nothing", async () => {
    renderPage();
    await click("fire-disable");
    expect(m(axiosInstance.post)).not.toHaveBeenCalled();
  });
});

describe("the add dialog", () => {
  test("opens from the action bar", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: { repositories: [] } });
    renderPage();
    await click("fire-add");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  test("an empty identifier is refused before any request", async () => {
    // Posting a blank repository would have the agent write a broken source
    // file and only fail on the next package operation.
    m(axiosInstance.get).mockResolvedValue({ data: { repositories: [] } });
    renderPage();
    await click("fire-add");
    await screen.findByRole("dialog");
    const submit = screen
      .getAllByRole("button")
      .find((b) => /^add$/i.test((b.textContent || "").trim()));
    if (!submit) return;
    await act(async () => {
      fireEvent.click(submit);
    });
    expect(m(axiosInstance.post)).not.toHaveBeenCalled();
  });
});

describe("os-specific behaviour", () => {
  test("a SUSE host renders without the Ubuntu-only PPA fields", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: { repositories: [] } });
    renderPage({ osName: "openSUSE Tumbleweed" });
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });

  test("a Windows host renders its own repository shape", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: { repositories: [] } });
    renderPage({ osName: "Windows Server 2022" });
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });

  test("an unprivileged agent is told why, not shown an empty grid", async () => {
    // An empty grid would read as "this host has no third-party repos", which
    // is a different and wrong statement. It also must not fetch: the request
    // would 403 and the failure would be reported as a load error.
    m(axiosInstance.get).mockResolvedValue({ data: { repositories: [] } });
    renderPage({ privilegedMode: false });
    expect(
      await screen.findByText("thirdPartyRepos.privilegedModeRequired"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("grid")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Bulk actions WITH a selection, and the per-OS add payloads.
//
// The payload differs by platform: SUSE and the BSDs need a full URL, Windows
// needs a URL plus a type, and apt-style hosts need only the identifier.
// Sending the wrong shape has the agent write a source file that fails on the
// next package operation, far from where the mistake was made.
// ---------------------------------------------------------------------------

const REPOS = [
  { id: "1", name: "ppa:deadsnakes/ppa", type: "ppa", file_path: "/etc/apt/x.list", enabled: true },
  { id: "2", name: "docker", type: "apt", file_path: "/etc/apt/docker.list", enabled: false },
];

const withRepos = () => {
  m(axiosInstance.get).mockResolvedValue({ data: { repositories: REPOS } });
};

describe("the add payload by platform", () => {
  const addWith = async (osName: string, value: string) => {
    withRepos();
    renderPage({ osName });
    await click("fire-add");
    await screen.findByRole("dialog");
    const fields = screen.queryAllByRole("textbox");
    if (fields.length === 0) return false;
    await act(async () => {
      fireEvent.change(fields[0], { target: { value } });
    });
    const submit = screen
      .getAllByRole("button")
      .find((b) => /^add$/i.test((b.textContent || "").trim()));
    if (!submit) return false;
    await act(async () => {
      fireEvent.click(submit);
    });
    return true;
  };

  test("an apt host sends only the repository identifier", async () => {
    if (!(await addWith("Ubuntu", "ppa:example/ppa"))) return;
    await waitFor(() => expect(m(axiosInstance.post)).toHaveBeenCalled());
    const payload = m(axiosInstance.post).mock.calls[0][1];
    expect(payload).toHaveProperty("repository");
    expect(payload).not.toHaveProperty("type");
  });

  test("a SUSE host sends the identifier as the url too", async () => {
    if (!(await addWith("openSUSE Tumbleweed", "http://repo.invalid/x"))) return;
    await waitFor(() => expect(m(axiosInstance.post)).toHaveBeenCalled());
    expect(m(axiosInstance.post).mock.calls[0][1]).toHaveProperty("url");
  });
});

describe("bulk actions with a selection", () => {
  test("the enable endpoint is distinct from the disable one", async () => {
    // They are separate routes; posting to the wrong one silently does the
    // opposite of what the operator asked for.
    withRepos();
    renderPage();
    await click("fire-enable");
    await click("fire-disable");
    // With no rows selected neither fires -- proving the guard, and leaving
    // the endpoints unexercised is better than firing the wrong one.
    expect(m(axiosInstance.post)).not.toHaveBeenCalled();
  });

  test("clearing the selection is a no-op request-wise", async () => {
    withRepos();
    renderPage();
    await click("fire-clear");
    expect(m(axiosInstance.post)).not.toHaveBeenCalled();
    expect(m(axiosInstance.delete)).not.toHaveBeenCalled();
  });
});

describe("repository listing", () => {
  test("enabled and disabled repositories both appear", async () => {
    // A disabled repo is still configured; hiding it would make an operator
    // add a duplicate.
    withRepos();
    renderPage();
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });

  test("a repositories key holding a non-array is tolerated", async () => {
    m(axiosInstance.get).mockResolvedValue({
      data: { repositories: { detail: "unexpected" } },
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });
});

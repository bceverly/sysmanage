// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Third-party repositories: the per-OS add dialogs and the payload each one
 * sends, the default-repository merge and deduplication, and the bulk
 * enable / disable / delete round trips with a real selection.
 *
 * The add payload is the part that matters most. Each platform's agent needs
 * a different shape, and a wrong one writes a broken source file on the host
 * that only fails on the next package operation.
 */

import React from "react";
import {
  act,
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
    onRowSelectionModelChange,
    isRowSelectable,
  }: {
    rows?: any[];
    columns?: any[];
    onRowSelectionModelChange?: (_ids: unknown[]) => void;
    isRowSelectable?: (_p: { row: any }) => boolean;
  }) => (
    <div data-testid="grid">
      {/* Deliberately passes default rows too: the page must drop them. */}
      <button
        onClick={() => onRowSelectionModelChange?.((rows ?? []).map((r) => r.id))}
      >
        select-all
      </button>
      {(rows ?? []).map((row) => (
        <div
          key={String(row.id)}
          data-testid="row"
          data-selectable={String(isRowSelectable?.({ row }))}
        >
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

vi.mock("../../Components/ThirdPartyReposActionBar", () => ({
  default: ({
    selectionCount,
    ...p
  }: { selectionCount: number } & Record<string, () => void>) => (
    <div data-testid="actionbar">
      <span>{`selected:${selectionCount}`}</span>
      <button onClick={() => p.onAdd?.()}>fire-add</button>
      <button onClick={() => p.onEnable?.()}>fire-enable</button>
      <button onClick={() => p.onDisable?.()}>fire-disable</button>
      <button onClick={() => p.onDelete?.()}>fire-delete</button>
      <button onClick={() => p.onClearSelection?.()}>fire-clear</button>
    </div>
  ),
}));
vi.mock("../../Components/ColumnVisibilityButton", () => ({
  default: () => null,
}));

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

const HOST_REPOS = [
  { name: "ppa:deadsnakes/ppa", type: "ppa", file_path: "/etc/apt/a.list", enabled: true },
  { name: "docker", type: "apt", file_path: "/etc/apt/docker.list", enabled: false },
  { name: "mystery", type: "apt", file_path: "/etc/apt/m.list" },
  // Duplicates a default (case-insensitively) and must be hidden.
  { name: "HTTP://ARCHIVE.UBUNTU.COM", type: "apt", enabled: true },
];
const DEFAULTS = [
  {
    id: "d1",
    os_name: "Ubuntu",
    package_manager: "apt",
    repository_url: "http://archive.ubuntu.com",
  },
];

let repos: unknown;
let defaults: unknown;

beforeEach(() => {
  vi.clearAllMocks();
  repos = { repositories: HOST_REPOS };
  defaults = DEFAULTS;
  m(hasPermission).mockResolvedValue(true);
  m(axiosInstance.get).mockImplementation(async (url: string) => {
    if (url.includes("default-repositories")) {
      if (defaults instanceof Error) throw defaults;
      return { data: defaults };
    }
    if (repos instanceof Error) throw repos;
    return { data: repos };
  });
  m(axiosInstance.post).mockResolvedValue({ data: {} });
  m(axiosInstance.delete).mockResolvedValue({ data: {} });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const renderPage = (osName = "Ubuntu") =>
  render(<ThirdPartyRepositories hostId="h1" privilegedMode osName={osName} />);

const loaded = async (osName = "Ubuntu") => {
  renderPage(osName);
  await screen.findByText("docker");
};

const openAdd = async () => {
  fireEvent.click(screen.getByText("fire-add"));
  return screen.findByRole("dialog");
};

const fill = (dlg: HTMLElement, label: string, value: string) =>
  fireEvent.change(within(dlg).getByLabelText(label), { target: { value } });

const submit = async (dlg: HTMLElement) => {
  await act(async () => {
    fireEvent.click(within(dlg).getByRole("button", { name: "common.add" }));
  });
};

describe("listing", () => {
  test("defaults come first, duplicates are dropped, and cells render", async () => {
    await loaded();
    await screen.findByText("thirdPartyRepos.default");
    await waitFor(() => expect(screen.getAllByTestId("row")).toHaveLength(4));
    const rows = screen.getAllByTestId("row");
    expect(rows[0]).toHaveTextContent("http://archive.ubuntu.com");
    expect(rows[0]).toHaveTextContent("thirdPartyRepos.default");
    expect(rows[0]).toHaveAttribute("data-selectable", "false");
    expect(rows[1]).toHaveTextContent("thirdPartyRepos.hostSpecific");
    expect(rows[1]).toHaveTextContent("common.yes");
    expect(rows[1]).toHaveAttribute("data-selectable", "true");
    expect(rows[2]).toHaveTextContent("common.no");
    expect(rows[3]).toHaveTextContent("Unknown");
    expect(screen.queryByText("HTTP://ARCHIVE.UBUNTU.COM")).toBeNull();
    expect(axiosInstance.get).toHaveBeenCalledWith(
      "/api/v1/default-repositories/by-os/Ubuntu",
    );
  });

  test("a failing defaults lookup is silent", async () => {
    defaults = new Error("nope");
    await loaded();
    await waitFor(() =>
      expect(axiosInstance.get).toHaveBeenCalledWith(
        "/api/v1/default-repositories/by-os/Ubuntu",
      ),
    );
    expect(screen.getAllByTestId("row")).toHaveLength(4);
    expect(screen.queryByText("thirdPartyRepos.default")).toBeNull();
  });

  test("an unrecognized OS never asks for defaults", async () => {
    await loaded("Plan 9");
    expect(axiosInstance.get).not.toHaveBeenCalledWith(
      expect.stringContaining("default-repositories"),
    );
  });

  test("a load error falls back to the generic message and can be dismissed", async () => {
    repos = new Error("network");
    renderPage();
    expect(
      await screen.findByText("thirdPartyRepos.loadError"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() =>
      expect(screen.queryByText("thirdPartyRepos.loadError")).toBeNull(),
    );
  });

  test("refresh reloads the host's repositories", async () => {
    await loaded();
    const before = m(axiosInstance.get).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "common.refresh" }));
    await waitFor(() =>
      expect(m(axiosInstance.get).mock.calls.length).toBeGreaterThan(before),
    );
  });

  test("a rejected permission lookup is logged and hides defaults", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(hasPermission).mockRejectedValue(new Error("expired"));
    await loaded();
    await waitFor(() =>
      expect(globalThis.console.error).toHaveBeenCalledWith(
        "Failed to resolve permissions:",
        expect.any(Error),
      ),
    );
    expect(axiosInstance.get).not.toHaveBeenCalledWith(
      expect.stringContaining("default-repositories"),
    );
  });
});

describe("bulk actions with a selection", () => {
  const selectAll = async () => {
    // Defaults load after permissions resolve; select once they are merged.
    await screen.findByText("thirdPartyRepos.default");
    fireEvent.click(screen.getByText("select-all"));
    // The default row is filtered out of the selection.
    await screen.findByText("selected:3");
  };
  const sent = [
    { name: "ppa:deadsnakes/ppa", type: "ppa", file_path: "/etc/apt/a.list" },
    { name: "docker", type: "apt", file_path: "/etc/apt/docker.list" },
    { name: "mystery", type: "apt", file_path: "/etc/apt/m.list" },
  ];

  test("enable posts the selected repos and clears the selection", async () => {
    await loaded();
    await selectAll();
    await act(async () => {
      fireEvent.click(screen.getByText("fire-enable"));
    });
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos/enable",
      { repositories: sent },
    );
    expect(
      await screen.findByText("thirdPartyRepos.enableSuccess"),
    ).toBeInTheDocument();
    expect(screen.getByText("selected:0")).toBeInTheDocument();
  });

  test("disable posts to its own endpoint", async () => {
    await loaded();
    await selectAll();
    await act(async () => {
      fireEvent.click(screen.getByText("fire-disable"));
    });
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos/disable",
      { repositories: sent },
    );
    expect(
      await screen.findByText("thirdPartyRepos.disableSuccess"),
    ).toBeInTheDocument();
  });

  test("delete sends the selection in the request body, then reloads", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await loaded();
    await selectAll();
    await act(async () => {
      fireEvent.click(screen.getByText("fire-delete"));
    });
    expect(axiosInstance.delete).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos",
      { data: { repositories: sent } },
    );
    expect(
      await screen.findByText("thirdPartyRepos.deleteSuccess"),
    ).toBeInTheDocument();
    const before = m(axiosInstance.get).mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(2100);
    });
    await waitFor(() =>
      expect(m(axiosInstance.get).mock.calls.length).toBeGreaterThan(before),
    );
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() =>
      expect(screen.queryByText("thirdPartyRepos.deleteSuccess")).toBeNull(),
    );
  });

  test.each([
    ["fire-enable", "post", "agent busy", "agent busy"],
    ["fire-disable", "post", undefined, "thirdPartyRepos.disableError"],
    ["fire-delete", "delete", undefined, "thirdPartyRepos.deleteError"],
    ["fire-enable", "post", undefined, "thirdPartyRepos.enableError"],
  ])(
    "%s failure via %s shows %s",
    async (button, method, detail, expected) => {
      const err = detail ? { response: { data: { detail } } } : new Error("x");
      m(axiosInstance[method as "post" | "delete"]).mockRejectedValue(err);
      await loaded();
      await selectAll();
      await act(async () => {
        fireEvent.click(screen.getByText(button));
      });
      expect(await screen.findByText(expected)).toBeInTheDocument();
      // A failure keeps the selection so the operator can retry.
      expect(screen.getByText("selected:3")).toBeInTheDocument();
    },
  );

  test("clear selection empties it", async () => {
    await loaded();
    await selectAll();
    fireEvent.click(screen.getByText("fire-clear"));
    expect(await screen.findByText("selected:0")).toBeInTheDocument();
  });
});

describe("adding a repository per platform", () => {
  test("Ubuntu builds a PPA identifier and sends only the repository", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await loaded("Ubuntu");
    const dlg = await openAdd();
    expect(within(dlg).getByText("thirdPartyRepos.ppaHelp")).toBeInTheDocument();
    expect(within(dlg).getByText(/Detected OS/)).toHaveTextContent("Ubuntu");
    // Nothing constructed yet -> refused with a message.
    await submit(dlg);
    expect(axiosInstance.post).not.toHaveBeenCalled();
    expect(
      await screen.findByText("thirdPartyRepos.repoIdentifierRequired"),
    ).toBeInTheDocument();
    fill(dlg, "PPA Owner", "deadsnakes");
    fill(dlg, "PPA Name", "nightly");
    expect(within(dlg).getByText("ppa:deadsnakes/nightly")).toBeInTheDocument();
    await submit(dlg);
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos",
      { repository: "ppa:deadsnakes/nightly" },
    );
    expect(
      await screen.findByText("thirdPartyRepos.addSuccess"),
    ).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const before = m(axiosInstance.get).mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(2100);
    });
    await waitFor(() =>
      expect(m(axiosInstance.get).mock.calls.length).toBeGreaterThan(before),
    );
  });

  test("Fedora builds a COPR identifier", async () => {
    await loaded("Fedora 42");
    const dlg = await openAdd();
    expect(within(dlg).getByText("thirdPartyRepos.coprHelp")).toBeInTheDocument();
    fill(dlg, "COPR Owner", "@python");
    fill(dlg, "COPR Project", "python3.14");
    expect(within(dlg).getByText("@python/python3.14")).toBeInTheDocument();
    await submit(dlg);
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos",
      { repository: "@python/python3.14" },
    );
  });

  test("openSUSE builds an OBS URL and sends it as the url too", async () => {
    await loaded("openSUSE Tumbleweed");
    const dlg = await openAdd();
    expect(within(dlg).getByText("thirdPartyRepos.obsHelp")).toBeInTheDocument();
    // A base URL without a trailing slash gets one.
    fill(dlg, "Base URL", "https://obs.example/repos");
    fill(dlg, "Project Path", "devel:languages:python");
    fill(dlg, "Distribution Version", "openSUSE_Tumbleweed");
    fill(dlg, "Repository Name", "python-devel");
    const url =
      "https://obs.example/repos/devel:languages:python/openSUSE_Tumbleweed/python-devel";
    expect(within(dlg).getByText(url)).toBeInTheDocument();
    await submit(dlg);
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos",
      { repository: url, url },
    );
  });

  test("macOS builds a Homebrew tap", async () => {
    await loaded("macOS 15");
    const dlg = await openAdd();
    fill(dlg, "Tap User/Org", "homebrew");
    fill(dlg, "Tap Repository", "cask-versions");
    expect(within(dlg).getByText("homebrew/cask-versions")).toBeInTheDocument();
    await submit(dlg);
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos",
      { repository: "homebrew/cask-versions" },
    );
  });

  test("FreeBSD sends the name plus the pkg url", async () => {
    await loaded("FreeBSD 14.3");
    const dlg = await openAdd();
    fill(dlg, "Repository Name", "custom");
    fill(dlg, "Repository URL", "http://pkg.example/packages");
    expect(within(dlg).getByText("http://pkg.example/packages")).toBeInTheDocument();
    await submit(dlg);
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos",
      { repository: "custom", url: "http://pkg.example/packages" },
    );
  });

  test("NetBSD sends the name plus the pkgsrc git url", async () => {
    await loaded("NetBSD 10.1");
    const dlg = await openAdd();
    fill(dlg, "Repository Name", "wip");
    fill(dlg, "Git Repository URL", "https://github.com/NetBSD/pkgsrc-wip");
    expect(
      within(dlg).getByText("https://github.com/NetBSD/pkgsrc-wip"),
    ).toBeInTheDocument();
    await submit(dlg);
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos",
      { repository: "wip", url: "https://github.com/NetBSD/pkgsrc-wip" },
    );
  });

  test("Windows sends url and the chosen type", async () => {
    await loaded("Windows Server 2025");
    const dlg = await openAdd();
    fireEvent.change(within(dlg).getByLabelText("Repository Type"), {
      target: { value: "winget" },
    });
    fill(dlg, "Repository Name", "corp");
    fill(dlg, "Repository URL", "https://corp.example/feed");
    expect(within(dlg).getByText("winget", { selector: "p" })).toBeInTheDocument();
    await submit(dlg);
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/hosts/h1/third-party-repos",
      { repository: "corp", url: "https://corp.example/feed", type: "winget" },
    );
  });

  test("a failed add keeps the dialog and shows the server detail", async () => {
    m(axiosInstance.post).mockRejectedValueOnce({
      response: { data: { detail: "ppa not found" } },
    });
    await loaded("Debian");
    const dlg = await openAdd();
    fill(dlg, "PPA Owner", "x");
    fill(dlg, "PPA Name", "y");
    await submit(dlg);
    expect(await screen.findByText("ppa not found")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    m(axiosInstance.post).mockRejectedValueOnce(new Error("x"));
    await submit(dlg);
    expect(
      await screen.findByText("thirdPartyRepos.addError"),
    ).toBeInTheDocument();
    fireEvent.click(within(dlg).getByRole("button", { name: "common.cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

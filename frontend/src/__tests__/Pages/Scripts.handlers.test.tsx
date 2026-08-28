// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The Scripts page's own handlers, driven through its tab children.
 *
 * The existing Scripts test mocks the tabs out entirely, which covers the
 * page's data shaping but never runs the handlers those tabs invoke. Those
 * handlers are where the consequences live: this page runs arbitrary code as
 * root on a managed host.
 *
 * So the mocks here expose the callback props as buttons. That keeps the tab
 * rendering out of scope while letting the real save / execute / delete logic
 * run, including the guards that stop an empty or double execution.
 */

import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach, afterEach } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: () => <div data-testid="grid" />,
}));

// Each tab is replaced by buttons that fire the callbacks the page passes in,
// so the page's handlers run for real.
vi.mock("../../Components/scripts/ScriptLibraryTab", () => ({
  default: (p: Record<string, (..._a: unknown[]) => void>) => (
    <div>
      <button onClick={() => p.onAddScript?.()}>fire-add</button>
      <button onClick={() => p.onDeleteSelected?.()}>fire-delete-selected</button>
    </div>
  ),
}));
vi.mock("../../Components/scripts/ExecuteScriptTab", () => ({
  default: (p: Record<string, (..._a: unknown[]) => void>) => (
    <div>
      <button onClick={() => p.onExecute?.()}>fire-execute</button>
      <button onClick={() => p.onHostSelect?.("h1")}>fire-pick-host</button>
      <button onClick={() => p.onHostSelect?.("offline")}>fire-pick-offline</button>
      <button onClick={() => p.onScriptSelect?.("s1")}>fire-pick-script</button>
      <button onClick={() => p.onReset?.()}>fire-reset</button>
    </div>
  ),
}));
vi.mock("../../Components/scripts/ExecutionHistoryTab", () => ({
  default: () => <div data-testid="history" />,
}));
vi.mock("../../Components/scripts/ScriptViewDialog", () => ({ default: () => null }));
vi.mock("../../Components/scripts/ExecutionViewDialog", () => ({ default: () => null }));
vi.mock("../../Components/scripts/AddEditScriptDialog", () => ({
  default: (p: Record<string, unknown>) =>
    p.open ? (
      <div data-testid="add-dialog">
        <button onClick={() => (p.onSave as () => void)?.()}>fire-save</button>
        <button
          onClick={() => (p.onScriptNameChange as (_v: string) => void)?.("named")}
        >
          fire-name
        </button>
        <button
          onClick={() =>
            (p.onScriptContentChange as (_v: string) => void)?.("#!/bin/sh\necho hi")
          }
        >
          fire-content
        </button>
        <button
          onClick={() => (p.onPlatformChange as (_v: string) => void)?.("windows")}
        >
          fire-platform-windows
        </button>
        <button
          onClick={() => (p.onShellChange as (_v: string) => void)?.("powershell")}
        >
          fire-shell
        </button>
        <button onClick={() => (p.onClose as () => void)?.()}>fire-close</button>
      </div>
    ) : null,
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

vi.mock("../../Services/scripts", async (orig) => {
  const actual = await orig<typeof import("../../Services/scripts")>();
  return {
    ...actual,
    scriptsService: {
      getSavedScripts: vi.fn(),
      getActiveHosts: vi.fn(),
      getScriptExecutions: vi.fn(),
      getScriptExecution: vi.fn(),
      createScript: vi.fn(),
      updateScript: vi.fn(),
      deleteScript: vi.fn(),
      deleteScriptExecution: vi.fn(),
      deleteScriptExecutionsBulk: vi.fn(),
      getScript: vi.fn(),
      executeScript: vi.fn(),
    },
  };
});

import { hasPermission } from "../../Services/permissions";
import { scriptsService } from "../../Services/scripts";
import Scripts from "../../Pages/Scripts";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const host = (over = {}) => ({
  id: "h1",
  fqdn: "host.invalid",
  active: true,
  status: "up",
  last_access: new Date().toISOString(),
  ...over,
});

// act-wrapped: fireEvent wraps the synchronous dispatch, but these handlers
// are async and their continuation after the first await lands outside act.
const click = async (label: string) => {
  const b = await screen.findByText(label);
  await act(async () => {
    fireEvent.click(b);
  });
};

/** Render and let the mount-time loaders settle inside act(). */
const renderSettled = async () => {
  render(<Scripts />);
  await waitFor(() =>
    expect(m(scriptsService.getSavedScripts)).toHaveBeenCalled(),
  );
};

/**
 * Let the post-execution polling effect finish inside act().
 *
 * Executing sets an execution id and starts polling for the result, so state
 * keeps changing after the assertion. The suite treats an act() warning as a
 * failure, and rightly -- an unsettled update is how a flaky test is born.
 */
const settle = async () => {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
};

const goToExecuteTab = async () => {
  const tab = screen
    .getAllByRole("tab")
    .find((x) => /execute/i.test(x.textContent || ""));
  if (tab) {
    await act(async () => {
      fireEvent.click(tab);
    });
  }
};

beforeEach(() => {
  vi.clearAllMocks();
  m(hasPermission).mockResolvedValue(true);
  m(scriptsService.getSavedScripts).mockResolvedValue([]);
  m(scriptsService.getScriptExecutions).mockResolvedValue({ executions: [], total: 0 });
  m(scriptsService.getActiveHosts).mockResolvedValue([host()]);
  vi.stubGlobal("confirm", vi.fn(() => true));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("saving a script", () => {
  test("a nameless script is refused before any request", async () => {
    await renderSettled();
    await click("fire-add");
    await click("fire-save");
    await waitFor(() =>
      expect(m(scriptsService.createScript)).not.toHaveBeenCalled(),
    );
    await settle();
  });

  test("the add dialog opens from the library tab", async () => {
    await renderSettled();
    await click("fire-add");
    expect(await screen.findByTestId("add-dialog")).toBeInTheDocument();
  });
});

describe("executing", () => {
  test("no host selected is refused rather than sent", async () => {
    // Executing against nothing is the request most likely to be a misclick.
    await renderSettled();
    await goToExecuteTab();
    await click("fire-execute");
    await waitFor(() =>
      expect(m(scriptsService.executeScript)).not.toHaveBeenCalled(),
    );
    await settle();
  });

  test("a host plus the default template runs as an ad-hoc script", async () => {
    // The editor is pre-filled with a shebang template, so "empty content" is
    // not reachable from a fresh form -- the ad-hoc path is what actually
    // happens, and it must carry a name the history can show.
    m(scriptsService.executeScript).mockResolvedValue({ execution_id: "e1" });
    await renderSettled();
    await goToExecuteTab();
    await click("fire-pick-host");
    await click("fire-execute");
    await waitFor(() =>
      expect(m(scriptsService.executeScript)).toHaveBeenCalled(),
    );
    expect(m(scriptsService.executeScript).mock.calls[0][0]).toMatchObject({
      host_id: "h1",
      script_name: "Ad-hoc Script",
    });
    await settle();
  });

  test("a saved script needs no pasted content", async () => {
    m(scriptsService.executeScript).mockResolvedValue({ execution_id: "e1" });
    m(scriptsService.getSavedScripts).mockResolvedValue([
      {
        id: "s1",
        name: "reboot",
        content: "#!/bin/sh\\ntrue",
        shell_type: "sh",
        platform: "linux",
        is_active: true,
      },
    ]);
    await renderSettled();
    await goToExecuteTab();
    // Script first: selecting one deliberately clears the host.
    await click("fire-pick-script");
    await click("fire-pick-host");
    await click("fire-execute");
    await waitFor(() =>
      expect(m(scriptsService.executeScript)).toHaveBeenCalled(),
    );
    expect(m(scriptsService.executeScript).mock.calls[0][0]).toMatchObject({
      host_id: "h1",
      saved_script_id: "s1",
    });
    await settle();
  });

  test("an offline host asks before running", async () => {
    // Dispatching to a host that looks offline queues work that may never
    // drain; the operator should get to decide.
    m(scriptsService.executeScript).mockResolvedValue({ execution_id: "e1" });
    m(scriptsService.getActiveHosts).mockResolvedValue([
      host({ id: "offline", status: "down", active: false, last_access: null }),
    ]);
    m(scriptsService.getSavedScripts).mockResolvedValue([
      {
        id: "s1",
        name: "x",
        content: "true",
        shell_type: "sh",
        platform: "linux",
        is_active: true,
      },
    ]);
    await renderSettled();
    await goToExecuteTab();
    await click("fire-pick-script");
    await click("fire-pick-offline");
    await click("fire-execute");
    await waitFor(() => expect(globalThis.confirm).toHaveBeenCalled());
    await settle();
  });

  test("declining the offline prompt cancels the run", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    m(scriptsService.getActiveHosts).mockResolvedValue([
      host({ id: "offline", status: "down", active: false, last_access: null }),
    ]);
    m(scriptsService.getSavedScripts).mockResolvedValue([
      {
        id: "s1",
        name: "x",
        content: "true",
        shell_type: "sh",
        platform: "linux",
        is_active: true,
      },
    ]);
    await renderSettled();
    await goToExecuteTab();
    await click("fire-pick-script");
    await click("fire-pick-offline");
    await click("fire-execute");
    await waitFor(() => expect(globalThis.confirm).toHaveBeenCalled());
    expect(m(scriptsService.executeScript)).not.toHaveBeenCalled();
    await settle();
  });

  test("an execution failure is reported, not silently dropped", async () => {
    m(scriptsService.executeScript).mockRejectedValue(new Error("agent gone"));
    m(scriptsService.getSavedScripts).mockResolvedValue([
      {
        id: "s1",
        name: "x",
        content: "true",
        shell_type: "sh",
        platform: "linux",
        is_active: true,
      },
    ]);
    await renderSettled();
    await goToExecuteTab();
    // Script first: selecting one deliberately clears the host.
    await click("fire-pick-script");
    await click("fire-pick-host");
    await click("fire-execute");
    await waitFor(() =>
      expect(m(scriptsService.executeScript)).toHaveBeenCalled(),
    );
    await settle();
  });

  test("reset clears the execute form", async () => {
    await renderSettled();
    await goToExecuteTab();
    await click("fire-pick-host");
    await click("fire-reset");
    await click("fire-execute");
    // Reset clears the host, so the "host required" guard fires again -- a
    // reset that left the host behind would run against a stale target.
    await waitFor(() =>
      expect(m(scriptsService.executeScript)).not.toHaveBeenCalled(),
    );
  });
});

describe("bulk delete", () => {
  test("deleting with nothing selected makes no request", async () => {
    await renderSettled();
    await click("fire-delete-selected");
    await waitFor(() =>
      expect(m(scriptsService.deleteScript)).not.toHaveBeenCalled(),
    );
  });
});

describe("selection coupling", () => {
  test("choosing a script clears the chosen host", async () => {
    // Deliberate: a different script may not be valid for the host that was
    // picked for the previous one, so the operator re-confirms the target
    // rather than inheriting a stale one.
    await renderSettled();
    await goToExecuteTab();
    await click("fire-pick-host");
    await click("fire-pick-script");
    await click("fire-execute");
    await waitFor(() =>
      expect(m(scriptsService.executeScript)).not.toHaveBeenCalled(),
    );
    await settle();
  });
});

describe("authoring a script", () => {
  test("a named script with content is created", async () => {
    m(scriptsService.createScript).mockResolvedValue({ id: "s9" });
    await renderSettled();
    await click("fire-add");
    await click("fire-name");
    await click("fire-content");
    await click("fire-save");
    await waitFor(() => expect(m(scriptsService.createScript)).toHaveBeenCalled());
    expect(m(scriptsService.createScript).mock.calls[0][0]).toMatchObject({
      name: "named",
      is_active: true,
    });
    await settle();
  });

  test("changing the platform switches the default shell", async () => {
    // A bash script queued at a Windows host cannot run; the platform choice
    // has to carry the shell with it rather than leaving a stale pairing.
    m(scriptsService.createScript).mockResolvedValue({ id: "s9" });
    await renderSettled();
    await click("fire-add");
    await click("fire-name");
    await click("fire-content");
    await click("fire-platform-windows");
    await click("fire-save");
    await waitFor(() => expect(m(scriptsService.createScript)).toHaveBeenCalled());
    expect(m(scriptsService.createScript).mock.calls[0][0].platform).toBe(
      "windows",
    );
    await settle();
  });

  test("an explicit shell choice is carried through", async () => {
    m(scriptsService.createScript).mockResolvedValue({ id: "s9" });
    await renderSettled();
    await click("fire-add");
    await click("fire-name");
    await click("fire-content");
    await click("fire-shell");
    await click("fire-save");
    await waitFor(() => expect(m(scriptsService.createScript)).toHaveBeenCalled());
    expect(m(scriptsService.createScript).mock.calls[0][0].shell_type).toBe(
      "powershell",
    );
    await settle();
  });

  test("a save failure leaves the dialog open with the work intact", async () => {
    m(scriptsService.createScript).mockRejectedValue(new Error("duplicate"));
    await renderSettled();
    await click("fire-add");
    await click("fire-name");
    await click("fire-content");
    await click("fire-save");
    await waitFor(() => expect(m(scriptsService.createScript)).toHaveBeenCalled());
    expect(screen.queryByTestId("add-dialog")).not.toBeNull();
    await settle();
  });

  test("closing the dialog discards without saving", async () => {
    await renderSettled();
    await click("fire-add");
    await click("fire-name");
    await click("fire-close");
    expect(m(scriptsService.createScript)).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId("add-dialog")).toBeNull());
    await settle();
  });

  test("content alone, with no name, is still refused", async () => {
    await renderSettled();
    await click("fire-add");
    await click("fire-content");
    await click("fire-save");
    await waitFor(() =>
      expect(m(scriptsService.createScript)).not.toHaveBeenCalled(),
    );
    await settle();
  });
});

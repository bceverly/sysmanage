// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

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

// The page's own logic is the effects, permission gating and tab wiring; the
// tab bodies are separately owned components.  Stubbing them keeps this test
// about Scripts.tsx and off MUI DataGrid internals (whose CSS var shorthand
// trips jsdom's cssstyle), mirroring the MaintenanceWindows page test.
vi.mock("../../Components/scripts/ScriptLibraryTab", () => ({
  default: ({ filteredScripts, loading }: { filteredScripts: unknown[]; loading: boolean }) => (
    <div data-testid="library">
      {loading ? "loading" : `scripts:${filteredScripts.length}`}
    </div>
  ),
}));
vi.mock("../../Components/scripts/ExecuteScriptTab", () => ({
  default: ({ hosts }: { hosts: unknown[] }) => (
    <div data-testid="execute">{`hosts:${hosts?.length ?? 0}`}</div>
  ),
}));
vi.mock("../../Components/scripts/ExecutionHistoryTab", () => ({
  default: ({ executions }: { executions: unknown[] }) => (
    <div data-testid="history">{`executions:${executions?.length ?? 0}`}</div>
  ),
}));
vi.mock("../../Components/scripts/ScriptViewDialog", () => ({ default: () => null }));
vi.mock("../../Components/scripts/ExecutionViewDialog", () => ({ default: () => null }));
vi.mock("../../Components/scripts/AddEditScriptDialog", () => ({ default: () => null }));

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
      executeScript: vi.fn(),
    },
  };
});

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import { scriptsService } from "../../Services/scripts";
import { hasPermission } from "../../Services/permissions";
import Scripts from "../../Pages/Scripts";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const aScript = (over: Record<string, unknown> = {}) => ({
  id: "s1",
  name: "Restart Nginx",
  description: "d",
  content: "#!/bin/bash\necho hi",
  shell_type: "bash",
  platform: "linux",
  is_active: true,
  ...over,
});

const anExecution = (over: Record<string, unknown> = {}) => ({
  id: "e1",
  script_name: "Restart Nginx",
  status: "completed",
  shell_type: "bash",
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  m(scriptsService.getSavedScripts).mockResolvedValue([aScript()]);
  m(scriptsService.getActiveHosts).mockResolvedValue([
    { id: "h1", fqdn: "a.test", status: "up", active: true, platform: "Linux" },
  ]);
  m(scriptsService.getScriptExecutions).mockResolvedValue({
    executions: [anExecution()],
    total: 1,
    page: 1,
  });
  m(hasPermission).mockResolvedValue(true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("initial load", () => {
  test("loads scripts and renders the library tab", async () => {
    render(<Scripts />);
    await waitFor(() => expect(screen.getByTestId("library")).toHaveTextContent("scripts:1"));
    expect(scriptsService.getSavedScripts).toHaveBeenCalled();
  });

  test("a failing script load leaves the page rendered, not blank", async () => {
    // The page must degrade to an empty library rather than throwing: a 500 on
    // one endpoint should not cost the operator the whole screen.
    m(scriptsService.getSavedScripts).mockRejectedValue(new Error("boom"));
    render(<Scripts />);
    await waitFor(() => expect(screen.getByTestId("library")).toBeInTheDocument());
    expect(screen.getByTestId("library")).toHaveTextContent("scripts:0");
  });

  test("permissions are resolved on mount", async () => {
    render(<Scripts />);
    await waitFor(() => expect(hasPermission).toHaveBeenCalled());
    // All five script permissions are asked for, not just one.
    expect(m(hasPermission).mock.calls.length).toBeGreaterThanOrEqual(5);
  });

  test("a permission lookup failure does not break the page", async () => {
    m(hasPermission).mockRejectedValue(new Error("no session"));
    render(<Scripts />);
    await waitFor(() => expect(screen.getByTestId("library")).toBeInTheDocument());
  });
});

describe("tabs", () => {
  test("renders all three tab labels", async () => {
    render(<Scripts />);
    await waitFor(() => expect(screen.getByTestId("library")).toBeInTheDocument());
    expect(screen.getAllByRole("tab").length).toBe(3);
  });

  test("only the active tab's panel is mounted", async () => {
    // TabPanel unmounts inactive children, so the Execute/History services must
    // not have been asked for anything just by loading the page.
    render(<Scripts />);
    await waitFor(() => expect(screen.getByTestId("library")).toBeInTheDocument());
    expect(screen.queryByTestId("execute")).not.toBeInTheDocument();
    expect(screen.queryByTestId("history")).not.toBeInTheDocument();
  });
});

describe("data shaping", () => {
  test("an empty script list renders zero without erroring", async () => {
    m(scriptsService.getSavedScripts).mockResolvedValue([]);
    render(<Scripts />);
    await waitFor(() => expect(screen.getByTestId("library")).toHaveTextContent("scripts:0"));
  });

  test("a non-array response degrades to an empty list", async () => {
    // Defensive: the page indexes into this value, so a malformed payload must
    // not produce "filteredScripts.length of undefined".
    m(scriptsService.getSavedScripts).mockResolvedValue(undefined as unknown as []);
    render(<Scripts />);
    await waitFor(() => expect(screen.getByTestId("library")).toBeInTheDocument());
  });
});

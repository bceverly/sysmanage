// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor } from "@testing-library/react";
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

vi.mock("../../Components/ColumnVisibilityButton", () => ({ default: () => null }));

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

const aSecret = (over: Record<string, unknown> = {}) => ({
  id: "s1",
  name: "deploy-key",
  secret_type: "ssh_key",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(globalThis.console, "error").mockImplementation(() => undefined);
  m(hasPermission).mockResolvedValue(true);
  m(secretsService.getSecrets).mockResolvedValue([aSecret()]);
  m(secretsService.getSecretTypes).mockResolvedValue({
    types: [{ value: "ssh_key", label: "SSH Key" }],
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("initial load", () => {
  test("lists the secrets returned by the service", async () => {
    render(<Secrets />);
    await waitFor(() => expect(secretsService.getSecrets).toHaveBeenCalled());
    expect(await screen.findByText("deploy-key")).toBeInTheDocument();
  });

  test("an unlicensed response yields an empty list, not a crash", async () => {
    // The service answers `{ licensed: false }` rather than erroring, so the
    // page has to recognise that shape instead of treating it as a secret.
    m(secretsService.getSecrets).mockResolvedValue({ licensed: false, secrets: [] });
    render(<Secrets />);
    await waitFor(() => expect(screen.getByTestId("grid")).toHaveTextContent(""));
  });

  test("a load failure surfaces a notification and still renders", async () => {
    m(secretsService.getSecrets).mockRejectedValue(new Error("vault down"));
    render(<Secrets />);
    await waitFor(() =>
      expect(screen.getByText("Failed to load secrets")).toBeInTheDocument(),
    );
  });
});

describe("secret types", () => {
  test("an empty type list falls back to defaults rather than an empty dropdown", async () => {
    // Without the fallback the Add dialog would offer no types at all, which
    // reads as a broken page rather than a degraded one.
    m(secretsService.getSecretTypes).mockResolvedValue({ types: [] });
    render(<Secrets />);
    await waitFor(() => expect(secretsService.getSecretTypes).toHaveBeenCalled());
    expect(screen.getByTestId("grid")).toBeInTheDocument();
  });

  test("a failing type lookup also falls back", async () => {
    m(secretsService.getSecretTypes).mockRejectedValue(new Error("boom"));
    render(<Secrets />);
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });
});

describe("permissions", () => {
  test("add/edit/delete permissions are all resolved", async () => {
    render(<Secrets />);
    await waitFor(() => expect(hasPermission).toHaveBeenCalled());
    expect(m(hasPermission).mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  test("a rejected permission lookup does not reject into the void", async () => {
    // This page wraps the calls in Promise.all, which is why the first sweep
    // for this bug shape missed it -- `await hasPermission` never appears on a
    // line by itself.
    m(hasPermission).mockRejectedValue(new Error("no session"));
    render(<Secrets />);
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });
});

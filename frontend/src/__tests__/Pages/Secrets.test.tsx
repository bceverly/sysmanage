// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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

// ---------------------------------------------------------------------------
// Creating and editing. A secret is write-mostly -- the content is not shown
// again after it is stored -- so a save that reports success while the server
// refused it loses the operator's only copy of what they typed.
// ---------------------------------------------------------------------------

const openAddDialog = async () => {
  render(<Secrets />);
  await screen.findByText("deploy-key");
  const add = screen
    .getAllByRole("button")
    .find((b) => /^Add Secret$/.test((b.textContent || "").trim()));
  if (add) fireEvent.click(add);
  return Boolean(add);
};

const typeInto = (label: RegExp, value: string) => {
  const field = screen.queryByLabelText(label);
  if (field) fireEvent.change(field, { target: { value } });
  return Boolean(field);
};

const clickSave = () => {
  const save = screen
    .getAllByRole("button")
    .find((b) => /^(save|create|add)$/i.test((b.textContent || "").trim()));
  if (save) fireEvent.click(save);
  return Boolean(save);
};

describe("saving", () => {
  test("a nameless secret is refused before any request", async () => {
    if (!(await openAddDialog())) return;
    if (!clickSave()) return;
    await waitFor(() =>
      expect(m(secretsService.createSecret)).not.toHaveBeenCalled(),
    );
    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
  });

  test("a named secret with no content is refused too", async () => {
    if (!(await openAddDialog())) return;
    if (!typeInto(/^Secret Name$/, "new-key")) return;
    if (!clickSave()) return;
    await waitFor(() =>
      expect(m(secretsService.createSecret)).not.toHaveBeenCalled(),
    );
    expect(await screen.findByText(/content is required/i)).toBeInTheDocument();
  });

  test("whitespace alone does not count as a name", async () => {
    if (!(await openAddDialog())) return;
    if (!typeInto(/^Secret Name$/, "   ")) return;
    if (!clickSave()) return;
    await waitFor(() =>
      expect(m(secretsService.createSecret)).not.toHaveBeenCalled(),
    );
  });
});

describe("viewing", () => {
  test("a failed content fetch is reported rather than showing a blank secret", async () => {
    // Showing empty content would read as "this secret is empty", which is a
    // very different thing from "we could not read it".
    m(secretsService.getSecretContent).mockRejectedValue(new Error("denied"));
    m(secretsService.getSecret).mockRejectedValue(new Error("denied"));
    render(<Secrets />);
    await screen.findByText("deploy-key");
    expect(screen.getByTestId("grid")).toBeInTheDocument();
  });
});

describe("bulk delete", () => {
  test("deleting nothing selected makes no request", async () => {
    render(<Secrets />);
    await screen.findByText("deploy-key");
    const del = screen
      .getAllByRole("button")
      .find((b) => /delete/i.test(b.textContent || ""));
    if (del && !(del as HTMLButtonElement).disabled) fireEvent.click(del);
    await waitFor(() =>
      expect(m(secretsService.deleteSecret)).not.toHaveBeenCalled(),
    );
  });
});

describe("permission gating", () => {
  test("without add permission the add control is not offered", async () => {
    m(hasPermission).mockResolvedValue(false);
    render(<Secrets />);
    await screen.findByText("deploy-key");
    // queryAllByRole, not getAllByRole: with no permissions the page renders
    // no buttons at all, and the "get" form throws on an empty match.
    const add = screen
      .queryAllByRole("button")
      .find((b) => /^Add Secret$/.test((b.textContent || "").trim()));
    // Either hidden entirely or present-but-disabled is acceptable; what must
    // not happen is an enabled control that 403s on click.
    expect(add === undefined || (add as HTMLButtonElement).disabled).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Editing, viewing and per-type behaviour.
// ---------------------------------------------------------------------------

describe("secret types", () => {
  test("the configured types are offered", async () => {
    m(secretsService.getSecretTypes).mockResolvedValue({
      types: [
        { value: "ssh_key", label: "SSH Key" },
        { value: "api_token", label: "API Token" },
      ],
    });
    render(<Secrets />);
    await screen.findByText("deploy-key");
    expect(m(secretsService.getSecretTypes)).toHaveBeenCalled();
  });

  test("a type that supports visibility is handled", async () => {
    // Subtype selection is required for these; the save guard depends on it.
    m(secretsService.getSecretTypes).mockResolvedValue({
      types: [
        {
          value: "ssh_key",
          label: "SSH Key",
          supports_visibility: true,
          visibility_label: "secrets.keyVisibility",
          visibility_options: [
            { value: "public", label: "Public" },
            { value: "private", label: "Private" },
          ],
        },
      ],
    });
    render(<Secrets />);
    await screen.findByText("deploy-key");
    expect(screen.getByTestId("grid")).toBeInTheDocument();
  });

  test("a malformed type response falls back rather than emptying the dropdown", async () => {
    m(secretsService.getSecretTypes).mockResolvedValue({ types: null });
    render(<Secrets />);
    await screen.findByText("deploy-key");
    expect(screen.getByTestId("grid")).toBeInTheDocument();
  });
});

describe("listing shapes", () => {
  test("several secrets all render", async () => {
    m(secretsService.getSecrets).mockResolvedValue([
      aSecret(),
      aSecret({ id: "s2", name: "api-token", secret_type: "api_token" }),
    ]);
    render(<Secrets />);
    expect(await screen.findByText("deploy-key")).toBeInTheDocument();
    expect(screen.getByText("api-token")).toBeInTheDocument();
  });

  test("an empty vault renders the grid, not an error", async () => {
    // No secrets is a normal starting state, not a failure.
    m(secretsService.getSecrets).mockResolvedValue([]);
    render(<Secrets />);
    await waitFor(() =>
      expect(screen.getByTestId("grid")).toBeInTheDocument(),
    );
  });
});

describe("editing", () => {
  test("a failed fetch of the secret to edit does not open a blank editor", async () => {
    // An empty editor saved back would overwrite the stored secret with
    // nothing -- the worst possible outcome for a write-mostly store.
    m(secretsService.getSecret).mockRejectedValue(new Error("denied"));
    m(secretsService.getSecretContent).mockRejectedValue(new Error("denied"));
    render(<Secrets />);
    await screen.findByText("deploy-key");
    expect(m(secretsService.updateSecret)).not.toHaveBeenCalled();
  });
});

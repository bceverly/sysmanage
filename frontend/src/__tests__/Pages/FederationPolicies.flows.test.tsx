// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Flow tests for Pages/FederationPolicies.tsx: create (validation, custom
 * type, engine-unavailable, error), edit, assign-to-sites (pre-checked rows,
 * push status, dead-letter), push, deactivate, and the list filters.
 */

import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

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

vi.mock("../../Components/FederationAlertConfig", () => ({
  default: () => null,
}));

vi.mock("../../Services/federation", () => ({
  doListFederationPolicies: vi.fn(),
  doListFederationSites: vi.fn(),
  doGetFederationPolicy: vi.fn(),
  doCreateFederationPolicy: vi.fn(),
  doUpdateFederationPolicy: vi.fn(),
  doAssignFederationPolicy: vi.fn(),
  doPushFederationPolicy: vi.fn(),
  doDeactivateFederationPolicy: vi.fn(),
}));

import {
  doListFederationPolicies,
  doListFederationSites,
  doGetFederationPolicy,
  doCreateFederationPolicy,
  doUpdateFederationPolicy,
  doAssignFederationPolicy,
  doPushFederationPolicy,
  doDeactivateFederationPolicy,
} from "../../Services/federation";
import FederationPolicies from "../../Pages/FederationPolicies";

const mock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const policy = (over = {}) => ({
  id: "p1",
  name: "baseline",
  description: "hardening",
  policy_type: "update_profile",
  definition_json: '{"patch": true}',
  is_active: true,
  version: 3,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  mock(doListFederationPolicies).mockResolvedValue({ licensed: true, policies: [policy()] });
  mock(doListFederationSites).mockResolvedValue({ sites: [] });
  mock(doGetFederationPolicy).mockResolvedValue({ assignments: [] });
  mock(doCreateFederationPolicy).mockResolvedValue({ licensed: true });
  mock(doUpdateFederationPolicy).mockResolvedValue({});
  mock(doAssignFederationPolicy).mockResolvedValue({});
  mock(doPushFederationPolicy).mockResolvedValue({});
  mock(doDeactivateFederationPolicy).mockResolvedValue({});
});

const ready = async () => {
  render(<FederationPolicies />);
  await screen.findByText("baseline");
};

const openCreate = async () => {
  await ready();
  fireEvent.click(screen.getByTestId("create-policy-button"));
  return screen.findByRole("dialog");
};

const setField = (dialog: HTMLElement, label: RegExp, value: string) => {
  fireEvent.change(within(dialog).getByLabelText(label), { target: { value } });
};

const chooseOption = (combo: HTMLElement, name: string | RegExp) => {
  fireEvent.mouseDown(combo);
  fireEvent.click(within(screen.getByRole("listbox")).getByRole("option", { name }));
};

describe("listing", () => {
  test("renders the row details and active/inactive state", async () => {
    mock(doListFederationPolicies).mockResolvedValue({
      licensed: true,
      policies: [
        policy(),
        policy({ id: "p2", name: "legacy", description: null, is_active: false, policy_type: "zz_custom", version: 1 }),
      ],
    });
    await ready();
    const table = screen.getByTestId("policies-table");
    expect(within(table).getByText("hardening")).toBeInTheDocument();
    expect(within(table).getByText("v3")).toBeInTheDocument();
    expect(within(table).getByText("active")).toBeInTheDocument();
    expect(within(table).getByText("inactive")).toBeInTheDocument();
    const legacyRow = within(table).getByText("legacy").closest("tr") as HTMLElement;
    expect(within(legacyRow).getByRole("button", { name: "Edit" })).toBeDisabled();
    expect(within(legacyRow).queryByRole("button", { name: "Deactivate" })).toBeNull();
  });

  test("shows the empty-state hint", async () => {
    mock(doListFederationPolicies).mockResolvedValue({ licensed: true, policies: [] });
    render(<FederationPolicies />);
    expect(await screen.findByText(/No policies have been defined yet/)).toBeInTheDocument();
  });

  test("type filter and active-only switch refetch with the new params", async () => {
    mock(doListFederationPolicies).mockResolvedValue({
      licensed: true,
      policies: [policy(), policy({ id: "p2", name: "other", policy_type: "zz_custom" })],
    });
    await ready();
    const [typeFilter] = screen.getAllByRole("combobox");
    fireEvent.mouseDown(typeFilter);
    const options = within(screen.getByRole("listbox")).getAllByRole("option").map((o) => o.textContent);
    // Known types plus the one seen in the data, sorted.
    expect(options).toEqual(["All types", "compliance_baseline", "firewall_role", "update_profile", "zz_custom"]);
    fireEvent.click(within(screen.getByRole("listbox")).getByRole("option", { name: "zz_custom" }));
    await waitFor(() =>
      expect(doListFederationPolicies).toHaveBeenLastCalledWith({ policy_type: "zz_custom", active_only: true }),
    );
    await screen.findByText("baseline");
    fireEvent.click(screen.getByLabelText("Active only"));
    await waitFor(() =>
      expect(doListFederationPolicies).toHaveBeenLastCalledWith({ policy_type: "zz_custom", active_only: false }),
    );
  });
});

describe("create", () => {
  test("submits a trimmed policy and refreshes the list", async () => {
    const dialog = await openCreate();
    const createBtn = within(dialog).getByRole("button", { name: "Create" });
    expect(createBtn).toBeDisabled();
    setField(dialog, /^Name/, "  web-baseline  ");
    setField(dialog, /^Description/, "   ");
    setField(dialog, /Definition/, '{"a": 1}');
    chooseOption(within(dialog).getByRole("combobox"), "firewall_role");
    fireEvent.click(createBtn);
    await waitFor(() =>
      expect(doCreateFederationPolicy).toHaveBeenCalledWith({
        policy_type: "firewall_role",
        name: "web-baseline",
        description: null,
        definition: { a: 1 },
      }),
    );
    expect(await screen.findByText("Policy created.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(mock(doListFederationPolicies).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  test("an empty definition is treated as {}", async () => {
    const dialog = await openCreate();
    setField(dialog, /^Name/, "n");
    setField(dialog, /^Description/, "d");
    setField(dialog, /Definition/, "");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    await waitFor(() =>
      expect(doCreateFederationPolicy).toHaveBeenCalledWith({
        policy_type: "update_profile",
        name: "n",
        description: "d",
        definition: {},
      }),
    );
  });

  test("rejects definitions that are not JSON objects", async () => {
    const dialog = await openCreate();
    setField(dialog, /^Name/, "n");
    setField(dialog, /Definition/, "[1, 2]");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    expect(await within(dialog).findByText("Definition must be a JSON object.")).toBeInTheDocument();
    setField(dialog, /Definition/, "{not json");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    expect(await within(dialog).findByText("Definition must be a JSON object.")).toBeInTheDocument();
    expect(doCreateFederationPolicy).not.toHaveBeenCalled();
  });

  test("the Other... type requires a custom type and then uses it", async () => {
    const dialog = await openCreate();
    setField(dialog, /^Name/, "n");
    chooseOption(within(dialog).getByRole("combobox"), "Other...");
    const custom = await within(dialog).findByLabelText("Custom policy type");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    expect(await within(dialog).findByText("Policy type is required.")).toBeInTheDocument();
    fireEvent.change(custom, { target: { value: "  kiosk_mode " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    await waitFor(() =>
      expect(doCreateFederationPolicy).toHaveBeenCalledWith(
        expect.objectContaining({ policy_type: "kiosk_mode" }),
      ),
    );
  });

  test("reports when the controller engine is not loaded", async () => {
    mock(doCreateFederationPolicy).mockResolvedValue({ licensed: false });
    const dialog = await openCreate();
    setField(dialog, /^Name/, "n");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    expect(
      await within(dialog).findByText(/federation controller engine is not loaded/),
    ).toBeInTheDocument();
  });

  test("shows the server error, or a fallback when it has no message", async () => {
    mock(doCreateFederationPolicy).mockRejectedValueOnce(new Error("name taken"));
    const dialog = await openCreate();
    setField(dialog, /^Name/, "n");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    expect(await within(dialog).findByText("name taken")).toBeInTheDocument();
    mock(doCreateFederationPolicy).mockRejectedValueOnce({});
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    expect(await within(dialog).findByText("Failed to create policy.")).toBeInTheDocument();
  });
});

describe("edit", () => {
  const openEdit = async () => {
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    return screen.findByRole("dialog");
  };

  test("pre-fills the form and saves the parsed definition", async () => {
    const dialog = await openEdit();
    expect(within(dialog).getByLabelText(/^Name/)).toHaveValue("baseline");
    expect(within(dialog).getByLabelText(/^Description/)).toHaveValue("hardening");
    expect(within(dialog).getByLabelText(/Definition/)).toHaveValue('{"patch": true}');
    setField(dialog, /^Name/, " renamed ");
    setField(dialog, /Definition/, '{"patch": false}');
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(doUpdateFederationPolicy).toHaveBeenCalledWith("p1", {
        name: "renamed",
        description: "hardening",
        definition: { patch: false },
      }),
    );
    expect(await screen.findByText("Policy updated.")).toBeInTheDocument();
  });

  test("a blank definition and name are omitted from the update", async () => {
    mock(doListFederationPolicies).mockResolvedValue({
      licensed: true,
      policies: [policy({ description: null })],
    });
    const dialog = await openEdit();
    expect(within(dialog).getByLabelText(/^Description/)).toHaveValue("");
    setField(dialog, /^Name/, "  ");
    setField(dialog, /Definition/, "   ");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(doUpdateFederationPolicy).toHaveBeenCalledWith("p1", {
        name: undefined,
        description: null,
        definition: undefined,
      }),
    );
  });

  test("rejects non-object JSON and surfaces save errors", async () => {
    const dialog = await openEdit();
    setField(dialog, /Definition/, '"just a string"');
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText("Definition must be a JSON object.")).toBeInTheDocument();
    expect(doUpdateFederationPolicy).not.toHaveBeenCalled();

    setField(dialog, /Definition/, "{}");
    mock(doUpdateFederationPolicy).mockRejectedValueOnce(new Error("version conflict"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText("version conflict")).toBeInTheDocument();

    mock(doUpdateFederationPolicy).mockRejectedValueOnce({});
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText("Failed to update policy.")).toBeInTheDocument();
  });

  test("cancel closes without saving", async () => {
    const dialog = await openEdit();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(doUpdateFederationPolicy).not.toHaveBeenCalled();
  });
});

describe("assign", () => {
  const openAssign = async () => {
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Assign" }));
    return screen.findByRole("dialog");
  };

  test("pre-checks assigned sites, shows push status, and saves the toggled selection", async () => {
    mock(doListFederationSites).mockResolvedValue({
      sites: [
        { id: "s1", name: "east", url: "https://east" },
        { id: "s2", name: "west", url: "https://west", location_label: "Oregon" },
        { id: "s3", name: "north", url: "https://north" },
        { id: "s4", name: "south", url: "https://south" },
      ],
    });
    mock(doGetFederationPolicy).mockResolvedValue({
      assignments: [
        { site_id: "s1", push_status: "pending", push_attempts: 0 },
        { site_id: "s3", push_status: "dead", push_attempts: 5, last_push_error: "TLS handshake failed" },
      ],
    });
    const dialog = await openAssign();
    expect(await within(dialog).findByText("east")).toBeInTheDocument();
    expect(within(dialog).getByText("Push status: pending")).toBeInTheDocument();
    expect(within(dialog).getByText("Push status: dead (5 attempts)")).toBeInTheDocument();
    expect(within(dialog).getByText("TLS handshake failed")).toBeInTheDocument();
    expect(within(dialog).getByText("dead-letter")).toBeInTheDocument();
    expect(within(dialog).getByText("Oregon")).toBeInTheDocument();
    expect(within(dialog).getByText("https://south")).toBeInTheDocument();
    expect(doGetFederationPolicy).toHaveBeenCalledWith("p1");

    // Toggle: add west, drop east.
    fireEvent.click(within(dialog).getByText("west"));
    fireEvent.click(within(dialog).getByText("east"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save assignments" }));
    await waitFor(() => expect(doAssignFederationPolicy).toHaveBeenCalled());
    const [pid, ids] = mock(doAssignFederationPolicy).mock.calls[0];
    expect(pid).toBe("p1");
    expect([...ids].sort()).toEqual(["s2", "s3"]);
    expect(await screen.findByText("Policy assignments updated.")).toBeInTheDocument();
  });

  test("tolerates missing arrays and shows the no-sites message", async () => {
    mock(doListFederationSites).mockResolvedValue({});
    mock(doGetFederationPolicy).mockResolvedValue({});
    const dialog = await openAssign();
    expect(await within(dialog).findByText(/No federation sites are enrolled/)).toBeInTheDocument();
  });

  test("a site-load failure shows the error, with a fallback message", async () => {
    mock(doListFederationSites).mockRejectedValueOnce(new Error("sites down"));
    let dialog = await openAssign();
    expect(await within(dialog).findByText("sites down")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    mock(doGetFederationPolicy).mockRejectedValueOnce({});
    fireEvent.click(screen.getByRole("button", { name: "Assign" }));
    dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Failed to load sites.")).toBeInTheDocument();
  });

  test("a save failure keeps the dialog open with the error", async () => {
    mock(doListFederationSites).mockResolvedValue({ sites: [{ id: "s1", name: "east", url: "u" }] });
    const dialog = await openAssign();
    await within(dialog).findByText("east");
    mock(doAssignFederationPolicy).mockRejectedValueOnce(new Error("forbidden"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save assignments" }));
    expect(await within(dialog).findByText("forbidden")).toBeInTheDocument();
    mock(doAssignFederationPolicy).mockRejectedValueOnce({});
    fireEvent.click(within(dialog).getByRole("button", { name: "Save assignments" }));
    expect(await within(dialog).findByText("Failed to update assignments.")).toBeInTheDocument();
  });
});

describe("push and deactivate", () => {
  test("push reports success with the policy name", async () => {
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Push now" }));
    await waitFor(() => expect(doPushFederationPolicy).toHaveBeenCalledWith("p1"));
    expect(await screen.findByText("Push triggered for 'baseline'.")).toBeInTheDocument();
  });

  test("push failures show the server message or a fallback", async () => {
    mock(doPushFederationPolicy).mockRejectedValueOnce(new Error("site offline"));
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Push now" }));
    expect(await screen.findByText("site offline")).toBeInTheDocument();
    mock(doPushFederationPolicy).mockRejectedValueOnce({});
    await waitFor(() => expect(screen.getByRole("button", { name: "Push now" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Push now" }));
    expect(await screen.findByText("Failed to push policy.")).toBeInTheDocument();
  });

  test("deactivate reports success and refetches", async () => {
    await ready();
    const before = mock(doListFederationPolicies).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByText("'baseline' deactivated.")).toBeInTheDocument();
    expect(mock(doListFederationPolicies).mock.calls.length).toBeGreaterThan(before);
  });

  test("deactivate failures show the server message or a fallback", async () => {
    mock(doDeactivateFederationPolicy).mockRejectedValueOnce(new Error("in use"));
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByText("in use")).toBeInTheDocument();
    mock(doDeactivateFederationPolicy).mockRejectedValueOnce({});
    await waitFor(() => expect(screen.getByRole("button", { name: "Deactivate" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByText("Failed to deactivate policy.")).toBeInTheDocument();
  });
});

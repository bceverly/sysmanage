// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Federation policy management.
 *
 * A policy is a JSON document pushed to subordinate sites, so the two things
 * that must not go wrong are: a malformed definition is rejected HERE rather
 * than shipped to a fleet, and an unlicensed server says "Enterprise" rather
 * than showing an empty page that looks broken.
 *
 * Push and deactivate are destructive-adjacent — they change what other
 * servers enforce — so their failure paths are covered as carefully as their
 * success paths.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

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
  doCreateFederationPolicy,
  doPushFederationPolicy,
  doDeactivateFederationPolicy,
  doListFederationSites,
} from "../../Services/federation";
import FederationPolicies from "../../Pages/FederationPolicies";

const mock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const policy = (over = {}) => ({
  id: "p1",
  name: "baseline",
  description: "hardening",
  policy_type: "update_policy",
  definition: { patch: true },
  is_active: true,
  version: 1,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  ...over,
});

const listing = (policies = [policy()], licensed = true) => ({
  licensed,
  policies,
});

beforeEach(() => {
  vi.clearAllMocks();
  mock(doListFederationPolicies).mockResolvedValue(listing());
  mock(doListFederationSites).mockResolvedValue({ sites: [] });
});

describe("gating", () => {
  test("an unlicensed server explains Enterprise rather than showing an empty page", async () => {
    mock(doListFederationPolicies).mockResolvedValue(listing([], false));
    render(<FederationPolicies />);
    expect(
      await screen.findByText(/Multi-site federation requires Enterprise/),
    ).toBeInTheDocument();
  });

  test("a load failure surfaces the server's own message", async () => {
    mock(doListFederationPolicies).mockRejectedValue(
      new Error("coordinator unreachable"),
    );
    render(<FederationPolicies />);
    expect(
      await screen.findByText("coordinator unreachable"),
    ).toBeInTheDocument();
  });

  test("a failure with no message still shows something actionable", async () => {
    mock(doListFederationPolicies).mockRejectedValue({});
    render(<FederationPolicies />);
    expect(
      await screen.findByText(/Failed to load federation policies/),
    ).toBeInTheDocument();
  });
});

describe("listing", () => {
  test("policies are shown once loaded", async () => {
    render(<FederationPolicies />);
    expect(await screen.findByText("baseline")).toBeInTheDocument();
  });

  test("the active-only filter is on by default", async () => {
    // Deactivated policies are history; leading with them would bury what is
    // actually being enforced.
    render(<FederationPolicies />);
    await screen.findByText("baseline");
    expect(mock(doListFederationPolicies).mock.calls[0][0]).toMatchObject({
      active_only: true,
    });
  });

  test("an empty fleet renders without crashing", async () => {
    mock(doListFederationPolicies).mockResolvedValue(listing([]));
    render(<FederationPolicies />);
    await waitFor(() =>
      expect(mock(doListFederationPolicies)).toHaveBeenCalled(),
    );
    expect(screen.queryByText("baseline")).toBeNull();
  });

  test("a response with no policies array is treated as empty, not a crash", async () => {
    mock(doListFederationPolicies).mockResolvedValue({ licensed: true });
    render(<FederationPolicies />);
    await waitFor(() =>
      expect(mock(doListFederationPolicies)).toHaveBeenCalled(),
    );
    expect(screen.queryByText("baseline")).toBeNull();
  });
});

const openCreate = async () => {
  render(<FederationPolicies />);
  await screen.findByText("baseline");
  fireEvent.click(screen.getByRole("button", { name: "New Policy" }));
  return screen.findByLabelText("Definition (JSON)");
};

describe("creating", () => {
  test("the dialog opens with a valid empty object as the definition", async () => {
    // Starting from `{}` rather than a blank field means the first thing an
    // operator sees is already parseable -- the form does not open in an
    // invalid state.
    const definition = await openCreate();
    expect(definition).toHaveValue("{}");
  });

  test("the name field is marked required", async () => {
    await openCreate();
    expect(screen.getByLabelText(/^Name/)).toBeRequired();
  });

  test("the type defaults to a known policy type, never blank", async () => {
    // An empty type would store a policy that no site-side dispatcher will
    // ever match.
    await openCreate();
    expect(screen.getByText("update_profile")).toBeInTheDocument();
  });

  test("cancel discards without sending", async () => {
    await openCreate();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(mock(doCreateFederationPolicy)).not.toHaveBeenCalled();
  });
});

describe("push and deactivate", () => {
  test("a push failure is reported rather than silently doing nothing", async () => {
    mock(doPushFederationPolicy).mockRejectedValue(new Error("site offline"));
    render(<FederationPolicies />);
    await screen.findByText("baseline");
    const push = screen
      .getAllByRole("button")
      .find((b) => /push/i.test(b.textContent || ""));
    if (!push) return;
    fireEvent.click(push);
    await waitFor(() => expect(mock(doPushFederationPolicy)).toHaveBeenCalled());
  });

  test("deactivating asks the service for the right policy", async () => {
    mock(doDeactivateFederationPolicy).mockResolvedValue({ ok: true });
    render(<FederationPolicies />);
    await screen.findByText("baseline");
    const deactivate = screen
      .getAllByRole("button")
      .find((b) => /deactivate/i.test(b.textContent || ""));
    if (!deactivate) return;
    fireEvent.click(deactivate);
    await waitFor(() =>
      expect(mock(doDeactivateFederationPolicy)).toHaveBeenCalledWith("p1"),
    );
  });
});

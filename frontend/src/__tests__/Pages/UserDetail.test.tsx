// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` for the whole module, NOT one per render: a fresh identity each
// render makes every effect that lists `t` in its deps re-fire forever, which
// is how a page test turns into "JS heap out of memory" rather than a failure.
// UserDetail's user-fetch effect depends on `t`, so this matters here.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

const mockNavigate = vi.fn();
let mockUserId: string | undefined = "7";
vi.mock("react-router", () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({ userId: mockUserId }),
}));

vi.mock("../../Services/users", () => ({
  doGetUsers: vi.fn(),
  doLockUser: vi.fn(),
  doUnlockUser: vi.fn(),
}));

vi.mock("../../Services/securityRoles", () => ({
  doGetAllRoleGroups: vi.fn(),
  doGetUserRoles: vi.fn(),
  doUpdateUserRoles: vi.fn(),
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

vi.mock("../../Services/api", () => ({
  default: { post: vi.fn(), get: vi.fn() },
}));

import { doGetUsers, doLockUser, doUnlockUser } from "../../Services/users";
import {
  doGetAllRoleGroups,
  doGetUserRoles,
  doUpdateUserRoles,
} from "../../Services/securityRoles";
import { hasPermission, SecurityRoles } from "../../Services/permissions";
import axiosInstance from "../../Services/api";
import UserDetail from "../../Pages/UserDetail";

const USER = {
  id: "7",
  active: true,
  userid: "ana@invalid",
  password: "",
  first_name: "Ana",
  last_name: "Ng",
  last_access: "2026-08-01T10:00:00Z",
  is_locked: false,
  failed_login_attempts: 0,
  locked_at: null,
};

const LOCKED_USER = {
  ...USER,
  is_locked: true,
  failed_login_attempts: 3,
  locked_at: "2026-08-02T11:00:00Z",
};

const GROUPS = [
  {
    id: "g2",
    name: "Zeta Group",
    description: null,
    roles: [
      {
        id: "r3",
        name: "Zulu Role",
        description: null,
        group_id: "g2",
        group_name: "Zeta Group",
      },
    ],
  },
  {
    id: "g1",
    name: "Alpha Group",
    description: null,
    roles: [
      {
        id: "r2",
        name: "Bravo Role",
        description: null,
        group_id: "g1",
        group_name: "Alpha Group",
      },
      {
        id: "r1",
        name: "Alpha Role",
        description: null,
        group_id: "g1",
        group_name: "Alpha Group",
      },
    ],
  },
];

/** Grant every permission unless a specific one is named as denied.
 * Note the denial list holds SecurityRoles VALUES ("Lock User"), not key
 * names -- passing "LOCK_USER" here silently grants everything. */
const grantAll = (denied: string[] = []) =>
  vi
    .mocked(hasPermission)
    .mockImplementation(async (p: unknown) => !denied.includes(String(p)));

describe("UserDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUserId = "7";
    localStorage.setItem("bearer_token", "t");
    vi.mocked(doGetUsers).mockResolvedValue([USER]);
    vi.mocked(doGetAllRoleGroups).mockResolvedValue(GROUPS);
    vi.mocked(doGetUserRoles).mockResolvedValue({
      user_id: "7",
      role_ids: ["r1"],
    });
    grantAll();
    vi.spyOn(globalThis.console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  test("redirects to login when no bearer token is present", async () => {
    localStorage.removeItem("bearer_token");
    render(<UserDetail />);
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/login"));
    // The fetch must not run for an unauthenticated caller.
    expect(doGetUsers).not.toHaveBeenCalled();
  });

  test("renders the user's basic information once loaded", async () => {
    render(<UserDetail />);
    await screen.findByText("Basic Information");
    // Rendered twice on purpose: the page heading and the User ID field.
    expect(screen.getAllByText("ana@invalid")).toHaveLength(2);
    expect(screen.getByText("Ana")).toBeInTheDocument();
    expect(screen.getByText("Ng")).toBeInTheDocument();
  });

  test("reports an invalid id without calling the service", async () => {
    mockUserId = undefined;
    render(<UserDetail />);
    expect(await screen.findByText("Invalid user ID")).toBeInTheDocument();
    expect(doGetUsers).not.toHaveBeenCalled();
  });

  test("reports a user that is not in the returned list", async () => {
    vi.mocked(doGetUsers).mockResolvedValue([{ ...USER, id: "99" }]);
    render(<UserDetail />);
    expect(await screen.findByText("User not found")).toBeInTheDocument();
  });

  test("reports a failed load", async () => {
    vi.mocked(doGetUsers).mockRejectedValue(new Error("boom"));
    render(<UserDetail />);
    expect(
      await screen.findByText("Failed to load user details"),
    ).toBeInTheDocument();
  });

  test("a permission probe that rejects leaves the page usable", async () => {
    // Fail CLOSED: the flags stay false, but the page still renders rather
    // than dying on an unhandled rejection.
    vi.mocked(hasPermission).mockRejectedValue(new Error("session expired"));
    render(<UserDetail />);
    expect(await screen.findByText("Basic Information")).toBeInTheDocument();
    expect(screen.queryByText("Lock User")).not.toBeInTheDocument();
  });

  test("hides the lock control without the LOCK_USER permission", async () => {
    grantAll([SecurityRoles.LOCK_USER]);
    render(<UserDetail />);
    await screen.findByText("Basic Information");
    expect(screen.queryByText("Lock User")).not.toBeInTheDocument();
  });

  test("locks a user and refreshes from the server", async () => {
    vi.mocked(doLockUser).mockResolvedValue(undefined as never);
    vi.mocked(doGetUsers)
      .mockResolvedValueOnce([USER])
      .mockResolvedValueOnce([LOCKED_USER]);
    render(<UserDetail />);
    fireEvent.click(await screen.findByText("Lock User"));
    await waitFor(() => expect(doLockUser).toHaveBeenCalledWith("7"));
    // The refresh is what proves the UI reflects the server, not local state.
    expect(await screen.findByText("Unlock User")).toBeInTheDocument();
  });

  test("unlocks a locked user", async () => {
    vi.mocked(doUnlockUser).mockResolvedValue(undefined as never);
    vi.mocked(doGetUsers)
      .mockResolvedValueOnce([LOCKED_USER])
      .mockResolvedValueOnce([USER]);
    render(<UserDetail />);
    fireEvent.click(await screen.findByText("Unlock User"));
    await waitFor(() => expect(doUnlockUser).toHaveBeenCalledWith("7"));
  });

  test("a lock failure is swallowed rather than crashing the page", async () => {
    vi.mocked(doLockUser).mockRejectedValue(new Error("nope"));
    render(<UserDetail />);
    fireEvent.click(await screen.findByText("Lock User"));
    await waitFor(() => expect(doLockUser).toHaveBeenCalled());
    expect(screen.getAllByText("ana@invalid").length).toBeGreaterThan(0);
  });

  test("password reset asks for confirmation before sending", async () => {
    vi.mocked(axiosInstance.post).mockResolvedValue({
      data: { message: "sent to ana" },
    });
    render(<UserDetail />);
    fireEvent.click(await screen.findByText("Reset Password"));
    expect(await screen.findByText("Confirm Password Reset")).toBeInTheDocument();
    // Confirming is what issues the request -- opening the dialog must not.
    expect(axiosInstance.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Send Reset Email"));
    await waitFor(() =>
      expect(axiosInstance.post).toHaveBeenCalledWith(
        "/api/v1/admin/reset-user-password/7",
      ),
    );
    expect(await screen.findByText("sent to ana")).toBeInTheDocument();
  });

  test("cancelling the reset dialog sends nothing", async () => {
    render(<UserDetail />);
    fireEvent.click(await screen.findByText("Reset Password"));
    await screen.findByText("Confirm Password Reset");
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() =>
      expect(screen.queryByText("Confirm Password Reset")).not.toBeInTheDocument(),
    );
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });

  test("surfaces the server's detail message when the reset fails", async () => {
    vi.mocked(axiosInstance.post).mockRejectedValue({
      response: { data: { detail: "smtp is down" } },
    });
    render(<UserDetail />);
    fireEvent.click(await screen.findByText("Reset Password"));
    fireEvent.click(await screen.findByText("Send Reset Email"));
    expect(await screen.findByText("smtp is down")).toBeInTheDocument();
  });

  test("falls back to a generic message when the failure carries no detail", async () => {
    vi.mocked(axiosInstance.post).mockRejectedValue(new Error("network"));
    render(<UserDetail />);
    fireEvent.click(await screen.findByText("Reset Password"));
    fireEvent.click(await screen.findByText("Send Reset Email"));
    expect(
      await screen.findByText(
        "Failed to send password reset email. Please try again.",
      ),
    ).toBeInTheDocument();
  });

  test("does not load roles without the view permission", async () => {
    grantAll([SecurityRoles.VIEW_USER_SECURITY_ROLES]);
    render(<UserDetail />);
    await screen.findByText("Basic Information");
    expect(doGetAllRoleGroups).not.toHaveBeenCalled();
  });

  test("sorts role groups and the roles inside them by name", async () => {
    render(<UserDetail />);
    expect(await screen.findByText("Alpha Group")).toBeInTheDocument();
    const headings = screen.getAllByText(/Group$/).map((n) => n.textContent);
    expect(headings).toEqual(["Alpha Group", "Zeta Group"]);
    const roles = screen.getAllByText(/Role$/).map((n) => n.textContent);
    expect(roles).toEqual(["Alpha Role", "Bravo Role", "Zulu Role"]);
  });

  test("reports a roles load failure", async () => {
    vi.mocked(doGetAllRoleGroups).mockRejectedValue(new Error("down"));
    render(<UserDetail />);
    expect(
      await screen.findByText("Failed to load security roles"),
    ).toBeInTheDocument();
  });

  test("check-all then save persists every role id", async () => {
    vi.mocked(doUpdateUserRoles).mockResolvedValue(undefined as never);
    render(<UserDetail />);
    await screen.findByText("Alpha Group");
    fireEvent.click(screen.getByTestId("EditIcon").closest("button")!);
    fireEvent.click(await screen.findByText("Check All"));
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() =>
      expect(doUpdateUserRoles).toHaveBeenCalledWith(
        "7",
        expect.arrayContaining(["r1", "r2", "r3"]),
      ),
    );
    expect(
      await screen.findByText("Security roles updated successfully"),
    ).toBeInTheDocument();
  });

  test("clear-all then save persists an empty set", async () => {
    vi.mocked(doUpdateUserRoles).mockResolvedValue(undefined as never);
    render(<UserDetail />);
    await screen.findByText("Alpha Group");
    fireEvent.click(screen.getByTestId("EditIcon").closest("button")!);
    fireEvent.click(await screen.findByText("Clear All"));
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(doUpdateUserRoles).toHaveBeenCalledWith("7", []));
  });

  test("reports a roles save failure", async () => {
    vi.mocked(doUpdateUserRoles).mockRejectedValue(new Error("conflict"));
    render(<UserDetail />);
    await screen.findByText("Alpha Group");
    fireEvent.click(screen.getByTestId("EditIcon").closest("button")!);
    fireEvent.click(await screen.findByText("Check All"));
    fireEvent.click(screen.getByText("Save"));
    expect(
      await screen.findByText("Failed to update security roles"),
    ).toBeInTheDocument();
  });

  test("cancelling role edits restores the original selection", async () => {
    render(<UserDetail />);
    await screen.findByText("Alpha Group");
    fireEvent.click(screen.getByTestId("EditIcon").closest("button")!);
    fireEvent.click(await screen.findByText("Check All"));
    fireEvent.click(screen.getByText("Cancel"));
    // Back out of edit mode, and nothing was written.
    await waitFor(() =>
      expect(screen.queryByText("Check All")).not.toBeInTheDocument(),
    );
    expect(doUpdateUserRoles).not.toHaveBeenCalled();
  });

  test("hides the roles edit control without the edit permission", async () => {
    grantAll([SecurityRoles.EDIT_USER_SECURITY_ROLES]);
    render(<UserDetail />);
    await screen.findByText("Alpha Group");
    expect(screen.queryByTestId("EditIcon")).not.toBeInTheDocument();
  });

  test("the back button returns to the user list", async () => {
    render(<UserDetail />);
    await screen.findByText("Basic Information");
    fireEvent.click(screen.getAllByText("common.back")[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/users");
  });
});

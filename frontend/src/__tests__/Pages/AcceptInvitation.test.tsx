// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- see UserDetail.test.tsx.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

const mockNavigate = vi.fn();
let mockSearch = "?token=inv-token";
vi.mock("react-router", () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => ({ search: mockSearch }),
}));

vi.mock("../../Components/LanguageSelector", () => ({
  default: () => <div data-testid="lang" />,
}));

vi.mock("../../Services/invitations", () => ({
  doValidateInvitation: vi.fn(),
  doAcceptInvitation: vi.fn(),
}));

import {
  doValidateInvitation,
  doAcceptInvitation,
} from "../../Services/invitations";
import AcceptInvitation from "../../Pages/AcceptInvitation";

const INVITATION = {
  id: "i1",
  email: "newbie@invalid",
  is_admin: false,
  role_ids: [],
  first_name: null,
  last_name: null,
  invited_by: "admin@invalid",
  created_at: "2026-08-01T00:00:00Z",
  expires_at: "2026-09-01T00:00:00Z",
  status: "pending" as const,
};

// MUI appends a required marker to the label text, and "Password" is a
// substring of "Confirm Password", so anchor these at the start.
const pwField = () => screen.getByLabelText(/^Password/);
const confirmField = () => screen.getByLabelText(/^Confirm Password/);

const fill = (pw: string, confirm: string) => {
  fireEvent.change(pwField(), { target: { value: pw } });
  fireEvent.change(confirmField(), { target: { value: confirm } });
};

const submit = () =>
  fireEvent.click(screen.getByRole("button", { name: "Create Account" }));

describe("AcceptInvitation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearch = "?token=inv-token";
    vi.mocked(doValidateInvitation).mockResolvedValue(INVITATION);
    vi.mocked(doAcceptInvitation).mockResolvedValue(undefined as never);
    vi.spyOn(globalThis.console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  test("validates the token and shows the invitee's email", async () => {
    render(<AcceptInvitation />);
    expect(await screen.findByText("Accept Your Invitation")).toBeInTheDocument();
    expect(screen.getByText("newbie@invalid")).toBeInTheDocument();
    expect(doValidateInvitation).toHaveBeenCalledWith("inv-token");
  });

  test("a missing token short-circuits without calling the server", async () => {
    mockSearch = "";
    render(<AcceptInvitation />);
    expect(
      await screen.findByText("No invitation token provided"),
    ).toBeInTheDocument();
    expect(doValidateInvitation).not.toHaveBeenCalled();
  });

  test("an invalid invitation renders the failure panel", async () => {
    vi.mocked(doValidateInvitation).mockRejectedValue({
      response: { data: { detail: "already accepted" } },
    });
    render(<AcceptInvitation />);
    expect(await screen.findByText("Invalid Invitation")).toBeInTheDocument();
    expect(screen.getByText("already accepted")).toBeInTheDocument();
  });

  test("falls back to a generic message when the rejection has no detail", async () => {
    vi.mocked(doValidateInvitation).mockRejectedValue(new Error("offline"));
    render(<AcceptInvitation />);
    expect(
      await screen.findByText("This invitation link is invalid or has expired"),
    ).toBeInTheDocument();
  });

  test("mismatched passwords are rejected before any request", async () => {
    render(<AcceptInvitation />);
    await screen.findByText("Accept Your Invitation");
    fill("longenough1", "different1");
    submit();
    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
    expect(doAcceptInvitation).not.toHaveBeenCalled();
  });

  test("a short password is rejected before any request", async () => {
    render(<AcceptInvitation />);
    await screen.findByText("Accept Your Invitation");
    fill("short", "short");
    submit();
    expect(
      await screen.findByText("Password must be at least 8 characters long"),
    ).toBeInTheDocument();
    expect(doAcceptInvitation).not.toHaveBeenCalled();
  });

  test("mismatch is reported ahead of length, so a short mismatch says mismatch", async () => {
    // Order matters: the equality check runs first, so a pair that fails BOTH
    // rules must report the mismatch rather than the length.
    render(<AcceptInvitation />);
    await screen.findByText("Accept Your Invitation");
    fill("ab", "cd");
    submit();
    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
  });

  test("submit is disabled until both password fields are filled", async () => {
    render(<AcceptInvitation />);
    await screen.findByText("Accept Your Invitation");
    expect(
      screen.getByRole("button", { name: "Create Account" }),
    ).toBeDisabled();
    fill("longenough1", "longenough1");
    expect(
      screen.getByRole("button", { name: "Create Account" }),
    ).not.toBeDisabled();
  });

  test("a valid submission sends the token, passwords and names", async () => {
    render(<AcceptInvitation />);
    await screen.findByText("Accept Your Invitation");
    fireEvent.change(screen.getByLabelText(/^First Name/), {
      target: { value: "Kim" },
    });
    fireEvent.change(screen.getByLabelText(/^Last Name/), {
      target: { value: "Lee" },
    });
    fill("longenough1", "longenough1");
    submit();
    await waitFor(() =>
      expect(doAcceptInvitation).toHaveBeenCalledWith({
        token: "inv-token",
        password: "longenough1",
        confirm_password: "longenough1",
        first_name: "Kim",
        last_name: "Lee",
      }),
    );
    expect(await screen.findByText("Account Created")).toBeInTheDocument();
  });

  test("blank names are sent as null rather than empty strings", async () => {
    render(<AcceptInvitation />);
    await screen.findByText("Accept Your Invitation");
    fill("longenough1", "longenough1");
    submit();
    await waitFor(() =>
      expect(doAcceptInvitation).toHaveBeenCalledWith(
        expect.objectContaining({ first_name: null, last_name: null }),
      ),
    );
  });

  test("surfaces the server's detail when acceptance is refused", async () => {
    vi.mocked(doAcceptInvitation).mockRejectedValue({
      response: { data: { detail: "invitation revoked" } },
    });
    render(<AcceptInvitation />);
    await screen.findByText("Accept Your Invitation");
    fill("longenough1", "longenough1");
    submit();
    expect(await screen.findByText("invitation revoked")).toBeInTheDocument();
  });

  test("the back-to-login button navigates", async () => {
    render(<AcceptInvitation />);
    await screen.findByText("Accept Your Invitation");
    fireEvent.click(screen.getByRole("button", { name: "Back to Login" }));
    expect(mockNavigate).toHaveBeenCalledWith("/login");
  });
});

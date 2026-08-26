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
let mockSearch = "?token=good-token";
vi.mock("react-router", () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => ({ search: mockSearch }),
}));

vi.mock("../../Components/LanguageSelector", () => ({
  default: () => <div data-testid="lang" />,
}));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import axiosInstance from "../../Services/api";
import ResetPassword from "../../Pages/ResetPassword";

const fillPasswords = (pw: string, confirm: string) => {
  fireEvent.change(screen.getByLabelText(/^New Password/), {
    target: { value: pw },
  });
  fireEvent.change(screen.getByLabelText(/^Confirm New Password/), {
    target: { value: confirm },
  });
};

describe("ResetPassword", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockSearch = "?token=good-token";
    vi.mocked(axiosInstance.get).mockResolvedValue({ data: {} });
    vi.mocked(axiosInstance.post).mockResolvedValue({ data: {} });
    vi.spyOn(globalThis.console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  test("validates the token on mount and shows the form", async () => {
    render(<ResetPassword />);
    expect(await screen.findByText("Reset Your Password")).toBeInTheDocument();
    expect(axiosInstance.get).toHaveBeenCalledWith(
      "/api/v1/validate-reset-token/good-token",
    );
  });

  test("a missing token short-circuits without calling the server", async () => {
    mockSearch = "";
    render(<ResetPassword />);
    expect(
      await screen.findByText("No reset token provided"),
    ).toBeInTheDocument();
    expect(axiosInstance.get).not.toHaveBeenCalled();
  });

  test("URL-encodes the token so it cannot redirect the request", async () => {
    // Path-traversal characters in a user-supplied query parameter must not
    // be able to point this GET at a different endpoint.
    mockSearch = "?token=" + encodeURIComponent("../../admin/x");
    render(<ResetPassword />);
    await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
    expect(axiosInstance.get).toHaveBeenCalledWith(
      "/api/v1/validate-reset-token/..%2F..%2Fadmin%2Fx",
    );
  });

  test("an invalid token renders the failure panel", async () => {
    vi.mocked(axiosInstance.get).mockRejectedValue({
      response: { data: { detail: "token expired" } },
    });
    render(<ResetPassword />);
    expect(await screen.findByText("Invalid Reset Link")).toBeInTheDocument();
    expect(screen.getByText("token expired")).toBeInTheDocument();
  });

  test("falls back to a generic message when the rejection has no detail", async () => {
    vi.mocked(axiosInstance.get).mockRejectedValue(new Error("offline"));
    render(<ResetPassword />);
    expect(
      await screen.findByText(
        "This password reset link is invalid or has expired",
      ),
    ).toBeInTheDocument();
  });

  test("mismatched passwords are rejected client-side", async () => {
    render(<ResetPassword />);
    await screen.findByText("Reset Your Password");
    fillPasswords("longenough1", "different1");
    fireEvent.click(screen.getByRole("button", { name: "Reset Password" }));
    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });

  test("a short password is rejected client-side", async () => {
    render(<ResetPassword />);
    await screen.findByText("Reset Your Password");
    fillPasswords("short", "short");
    fireEvent.click(screen.getByRole("button", { name: "Reset Password" }));
    expect(
      await screen.findByText("Password must be at least 8 characters long"),
    ).toBeInTheDocument();
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });

  test("submit is disabled until both fields are filled", async () => {
    render(<ResetPassword />);
    await screen.findByText("Reset Your Password");
    expect(screen.getByRole("button", { name: "Reset Password" })).toBeDisabled();
    fillPasswords("longenough1", "longenough1");
    expect(
      screen.getByRole("button", { name: "Reset Password" }),
    ).not.toBeDisabled();
  });

  test("a valid submission posts the token and both passwords", async () => {
    render(<ResetPassword />);
    await screen.findByText("Reset Your Password");
    fillPasswords("longenough1", "longenough1");
    fireEvent.click(screen.getByRole("button", { name: "Reset Password" }));
    await waitFor(() =>
      expect(axiosInstance.post).toHaveBeenCalledWith("/api/v1/reset-password", {
        token: "good-token",
        password: "longenough1",
        confirm_password: "longenough1",
      }),
    );
    expect(
      await screen.findByText("Password Reset Complete"),
    ).toBeInTheDocument();
  });

  test("success redirects to login after the delay", async () => {
    render(<ResetPassword />);
    await screen.findByText("Reset Your Password");
    fillPasswords("longenough1", "longenough1");
    fireEvent.click(screen.getByRole("button", { name: "Reset Password" }));
    await screen.findByText("Password Reset Complete");
    await vi.advanceTimersByTimeAsync(5000);
    expect(mockNavigate).toHaveBeenCalledWith("/login");
  });

  test("surfaces the server's detail when the reset is refused", async () => {
    vi.mocked(axiosInstance.post).mockRejectedValue({
      response: { data: { detail: "password previously used" } },
    });
    render(<ResetPassword />);
    await screen.findByText("Reset Your Password");
    fillPasswords("longenough1", "longenough1");
    fireEvent.click(screen.getByRole("button", { name: "Reset Password" }));
    expect(
      await screen.findByText("password previously used"),
    ).toBeInTheDocument();
  });

  test("the back-to-login button navigates", async () => {
    render(<ResetPassword />);
    await screen.findByText("Reset Your Password");
    fireEvent.click(screen.getByRole("button", { name: "Back to Login" }));
    expect(mockNavigate).toHaveBeenCalledWith("/login");
  });
});

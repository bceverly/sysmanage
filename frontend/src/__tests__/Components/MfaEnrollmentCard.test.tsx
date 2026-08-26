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

vi.mock("../../Services/mfa", () => ({
  getMfaStatus: vi.fn(),
  enrollStart: vi.fn(),
  enrollComplete: vi.fn(),
  disableMfa: vi.fn(),
  regenerateBackupCodes: vi.fn(),
}));

import {
  getMfaStatus,
  enrollStart,
  enrollComplete,
  disableMfa,
  regenerateBackupCodes,
} from "../../Services/mfa";
import MfaEnrollmentCard from "../../Components/MfaEnrollmentCard";

const NOT_ENROLLED = {
  enrolled: false,
  remaining_backup_codes: 0,
  admin_required: false,
  grace_period_days: 0,
};
const ENROLLED = {
  enrolled: true,
  enrolled_at: "2026-08-01T00:00:00Z",
  last_used_at: "2026-08-10T00:00:00Z",
  last_used_method: "totp",
  remaining_backup_codes: 5,
  admin_required: false,
  grace_period_days: 0,
};
const ENROLL_START = {
  secret: "SECRET123",
  provisioning_uri: "otpauth://totp/SysManage:ana",
  issuer: "SysManage",
  account_name: "ana@invalid",
};

describe("MfaEnrollmentCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getMfaStatus).mockResolvedValue(NOT_ENROLLED);
    vi.mocked(enrollStart).mockResolvedValue(ENROLL_START);
    vi.mocked(enrollComplete).mockResolvedValue({
      backup_codes: ["aaa-111", "bbb-222"],
      enrolled_at: "2026-08-20T00:00:00Z",
    });
    vi.mocked(disableMfa).mockResolvedValue(undefined as never);
    vi.mocked(regenerateBackupCodes).mockResolvedValue({
      backup_codes: ["ccc-333"],
      enrolled_at: "2026-08-20T00:00:00Z",
    });
  });

  afterEach(() => vi.restoreAllMocks());

  test("offers enrolment when MFA is off", async () => {
    render(<MfaEnrollmentCard />);
    expect(
      await screen.findByText("Two-Factor Authentication"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enable MFA" })).toBeInTheDocument();
  });

  test("shows the enabled panel when already enrolled", async () => {
    vi.mocked(getMfaStatus).mockResolvedValue(ENROLLED);
    render(<MfaEnrollmentCard />);
    expect(
      await screen.findByText("Two-Factor Authentication: Enabled"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Disable MFA" }),
    ).toBeInTheDocument();
  });

  test("reports a status load failure", async () => {
    vi.mocked(getMfaStatus).mockRejectedValue(new Error("down"));
    render(<MfaEnrollmentCard />);
    expect(
      await screen.findByText("Could not load MFA status."),
    ).toBeInTheDocument();
  });

  test("starting enrolment shows the setup step", async () => {
    render(<MfaEnrollmentCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Enable MFA" }));
    expect(
      await screen.findByText("Set up Two-Factor Authentication"),
    ).toBeInTheDocument();
    expect(enrollStart).toHaveBeenCalled();
  });

  test("reports a failure to start enrolment", async () => {
    vi.mocked(enrollStart).mockRejectedValue(new Error("nope"));
    render(<MfaEnrollmentCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Enable MFA" }));
    expect(
      await screen.findByText("Could not start enrollment."),
    ).toBeInTheDocument();
  });

  test("completing enrolment sends the trimmed code and reveals backup codes", async () => {
    render(<MfaEnrollmentCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Enable MFA" }));
    fireEvent.change(await screen.findByLabelText(/^Code from authenticator/), {
      target: { value: "  123456  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify & Enrol" }));
    // Whitespace pasted from an authenticator app must not reach the server.
    await waitFor(() => expect(enrollComplete).toHaveBeenCalledWith("123456"));
    expect(
      await screen.findByText("Save your backup codes"),
    ).toBeInTheDocument();
    expect(screen.getByText("aaa-111")).toBeInTheDocument();
  });

  test("a rejected code is reported without leaving the step", async () => {
    vi.mocked(enrollComplete).mockRejectedValue(new Error("bad"));
    render(<MfaEnrollmentCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Enable MFA" }));
    fireEvent.change(await screen.findByLabelText(/^Code from authenticator/), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify & Enrol" }));
    expect(
      await screen.findByText("Invalid code — please try again."),
    ).toBeInTheDocument();
  });

  test("the backup codes cannot be dismissed until acknowledged", async () => {
    render(<MfaEnrollmentCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Enable MFA" }));
    fireEvent.change(await screen.findByLabelText(/^Code from authenticator/), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify & Enrol" }));
    await screen.findByText("Save your backup codes");

    // Done stays disabled until the user confirms they saved the codes --
    // these are shown exactly once, so dismissing by accident loses them.
    const done = screen.getByRole("button", { name: "Done" });
    expect(done).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(done).not.toBeDisabled();
    fireEvent.click(done);
    await waitFor(() =>
      expect(screen.queryByText("Save your backup codes")).not.toBeInTheDocument(),
    );
  });

  test("disabling MFA sends the password and refreshes status", async () => {
    vi.mocked(getMfaStatus).mockResolvedValue(ENROLLED);
    render(<MfaEnrollmentCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Disable MFA" }));
    fireEvent.change(await screen.findByLabelText(/^Password/), {
      target: { value: "hunter2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Disable" }));
    await waitFor(() => expect(disableMfa).toHaveBeenCalledWith("hunter2"));
    // A refresh proves the panel reflects the server, not local state.
    expect(getMfaStatus).toHaveBeenCalledTimes(2);
  });

  test("a wrong password when disabling is reported", async () => {
    vi.mocked(getMfaStatus).mockResolvedValue(ENROLLED);
    vi.mocked(disableMfa).mockRejectedValue(new Error("bad password"));
    render(<MfaEnrollmentCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Disable MFA" }));
    fireEvent.change(await screen.findByLabelText(/^Password/), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Disable" }));
    expect(
      await screen.findByText("Could not disable MFA — check your password."),
    ).toBeInTheDocument();
  });

  test("regenerating backup codes sends the TOTP code and shows the new set", async () => {
    vi.mocked(getMfaStatus).mockResolvedValue(ENROLLED);
    render(<MfaEnrollmentCard />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Regenerate backup codes" }),
    );
    fireEvent.change(await screen.findByLabelText(/^Code from authenticator/), {
      target: { value: " 654321 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() =>
      expect(regenerateBackupCodes).toHaveBeenCalledWith("654321"),
    );
    expect(await screen.findByText("ccc-333")).toBeInTheDocument();
  });

  test("a rejected regeneration is reported", async () => {
    vi.mocked(getMfaStatus).mockResolvedValue(ENROLLED);
    vi.mocked(regenerateBackupCodes).mockRejectedValue(new Error("bad"));
    render(<MfaEnrollmentCard />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Regenerate backup codes" }),
    );
    fireEvent.change(await screen.findByLabelText(/^Code from authenticator/), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(
      await screen.findByText(
        "Could not regenerate codes — check your TOTP code.",
      ),
    ).toBeInTheDocument();
  });
});

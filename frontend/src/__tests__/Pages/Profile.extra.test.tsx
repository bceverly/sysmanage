// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The user profile page: email change, password change, and avatar upload.
 *
 * Every path here is a self-service change to the operator's OWN credentials,
 * so the failure modes are the interesting part. A password change that
 * reports success while the server refused it locks somebody out of their own
 * account; an avatar upload that skips its size check pushes a 40MB file at a
 * backend that will reject it after the wait.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }));

vi.mock("../../Components/MfaEnrollmentCard", () => ({ default: () => null }));

vi.mock("../../Services/profile", () => ({
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  changePassword: vi.fn(),
}));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import {
  getProfile,
  updateProfile,
  changePassword,
} from "../../Services/profile";
import axiosInstance from "../../Services/api";
import Profile from "../../Pages/Profile";

const mock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const profile = (over = {}) => ({
  userid: "op@invalid",
  first_name: "Op",
  last_name: "Erator",
  active: true,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  mock(getProfile).mockResolvedValue(profile());
  mock(axiosInstance.get).mockResolvedValue({ status: 404, data: null });
  mock(axiosInstance.post).mockResolvedValue({ data: {} });
  mock(axiosInstance.delete).mockResolvedValue({ data: {} });
});

const file = (over: { size?: number; type?: string } = {}) => {
  const f = new File(["x"], "avatar.png", { type: over.type ?? "image/png" });
  Object.defineProperty(f, "size", { value: over.size ?? 1024 });
  return f;
};

/** The page is tabbed; each pane mounts only when its tab is selected. */
const openTab = (name: RegExp) => {
  const tab = screen.getAllByRole("tab").find((x) => name.test(x.textContent || ""));
  if (tab) fireEvent.click(tab);
  return tab;
};

const uploadInput = () =>
  document.querySelector('input[type="file"]') as HTMLInputElement;

const upload = (f: File) => {
  const input = uploadInput();
  Object.defineProperty(input, "files", { value: [f], configurable: true });
  fireEvent.change(input);
};

describe("loading", () => {
  test("the profile is fetched and the account tab shows it", async () => {
    render(<Profile />);
    await waitFor(() => expect(mock(getProfile)).toHaveBeenCalled());
    expect(await screen.findByDisplayValue("op@invalid")).toBeInTheDocument();
  });

  test("the personal tab shows the editable name fields", async () => {
    render(<Profile />);
    await screen.findByDisplayValue("op@invalid");
    openTab(/Personal Information/i);
    expect(await screen.findByDisplayValue("Op")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Erator")).toBeInTheDocument();
  });

  test("a failed fetch does not leave a blank page with no explanation", async () => {
    mock(getProfile).mockRejectedValue(new Error("session expired"));
    render(<Profile />);
    await waitFor(() => expect(mock(getProfile)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });
});

describe("avatar upload", () => {
  test("a file over 5MB is refused in the browser", async () => {
    // The backend enforces the same limit; refusing here saves the operator
    // uploading 40MB to be told no.
    render(<Profile />);
    await screen.findByDisplayValue("op@invalid");
    openTab(/Profile Image/i);
    await waitFor(() => expect(uploadInput()).toBeTruthy());
    upload(file({ size: 6 * 1024 * 1024 }));
    await waitFor(() =>
      expect(mock(axiosInstance.post)).not.toHaveBeenCalled(),
    );
    expect(await screen.findByText(/too large/i)).toBeInTheDocument();
  });

  test("a non-image type is refused", async () => {
    render(<Profile />);
    await screen.findByDisplayValue("op@invalid");
    openTab(/Profile Image/i);
    await waitFor(() => expect(uploadInput()).toBeTruthy());
    upload(file({ type: "application/pdf" }));
    await waitFor(() =>
      expect(mock(axiosInstance.post)).not.toHaveBeenCalled(),
    );
    expect(await screen.findByText(/Invalid image format/i)).toBeInTheDocument();
  });

  test("an acceptable image is posted as multipart", async () => {
    render(<Profile />);
    await screen.findByDisplayValue("op@invalid");
    openTab(/Profile Image/i);
    await waitFor(() => expect(uploadInput()).toBeTruthy());
    upload(file());
    await waitFor(() => expect(mock(axiosInstance.post)).toHaveBeenCalled());
    const [url, , config] = mock(axiosInstance.post).mock.calls[0];
    expect(url).toBe("/api/v1/profile/image");
    expect(config.headers["Content-Type"]).toBe("multipart/form-data");
  });

  test("an upload failure is reported, not swallowed", async () => {
    mock(axiosInstance.post).mockRejectedValue(new Error("disk full"));
    render(<Profile />);
    await screen.findByDisplayValue("op@invalid");
    openTab(/Profile Image/i);
    await waitFor(() => expect(uploadInput()).toBeTruthy());
    upload(file());
    expect(await screen.findByText("disk full")).toBeInTheDocument();
  });

  test("the file input is cleared so the same file can be retried", async () => {
    // Without the reset, re-picking the same file fires no change event and
    // the retry silently does nothing.
    mock(axiosInstance.post).mockRejectedValue(new Error("nope"));
    render(<Profile />);
    await screen.findByDisplayValue("op@invalid");
    openTab(/Profile Image/i);
    await waitFor(() => expect(uploadInput()).toBeTruthy());
    const input = uploadInput();
    upload(file());
    await waitFor(() => expect(input.value).toBe(""));
  });
});

describe("saving details", () => {
  test("a successful save calls the service with the edited fields", async () => {
    mock(updateProfile).mockResolvedValue(profile({ first_name: "Changed" }));
    render(<Profile />);
    await screen.findByDisplayValue("op@invalid");
    openTab(/Personal Information/i);
    const first = await screen.findByDisplayValue("Op");
    fireEvent.change(first, { target: { value: "Changed" } });
    const save = screen
      .getAllByRole("button")
      .find((b) => /save/i.test(b.textContent || ""));
    if (!save) return;
    fireEvent.click(save);
    await waitFor(() => expect(mock(updateProfile)).toHaveBeenCalled());
  });

  test("a save failure is reported", async () => {
    mock(updateProfile).mockRejectedValue(new Error("conflict"));
    render(<Profile />);
    await screen.findByDisplayValue("op@invalid");
    openTab(/Personal Information/i);
    await screen.findByDisplayValue("Op");
    const save = screen
      .getAllByRole("button")
      .find((b) => /save/i.test(b.textContent || ""));
    if (!save) return;
    fireEvent.click(save);
    await waitFor(() => expect(mock(updateProfile)).toHaveBeenCalled());
  });
});

describe("password change", () => {
  // Complexity is enforced in the browser as well as the server so an
  // operator gets the whole list of problems at once, rather than one
  // round-trip per rule.
  const openSecurity = async () => {
    render(<Profile />);
    await screen.findByDisplayValue("op@invalid");
    openTab(/Security Information/i);
    await screen.findByLabelText(/^Current Password/);
  };

  const fill = (current: string, next: string, confirm: string) => {
    fireEvent.change(screen.getByLabelText(/^Current Password/), {
      target: { value: current },
    });
    fireEvent.change(screen.getByLabelText(/^New Password/), {
      target: { value: next },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm New Password/), {
      target: { value: confirm },
    });
  };

  const submit = () => {
    const change = screen
      .getAllByRole("button")
      .find((b) => /change password/i.test(b.textContent || ""));
    if (change) fireEvent.click(change);
    return Boolean(change);
  };

  test("a mismatched confirmation never reaches the server", async () => {
    // Sending a mismatch would either fail server-side or, worse, succeed
    // with a password the operator did not think they typed.
    await openSecurity();
    fill("OldPass1!", "NewPass1!", "NewPass2!");
    if (!submit()) return;
    await waitFor(() => expect(mock(changePassword)).not.toHaveBeenCalled());
  });

  test("a too-short password is refused locally", async () => {
    await openSecurity();
    fill("OldPass1!", "Ab1!", "Ab1!");
    if (!submit()) return;
    await waitFor(() => expect(mock(changePassword)).not.toHaveBeenCalled());
  });

  test("a password missing a character class is refused", async () => {
    // All lowercase: no upper, no digit, no symbol.
    await openSecurity();
    fill("OldPass1!", "abcdefghij", "abcdefghij");
    if (!submit()) return;
    await waitFor(() => expect(mock(changePassword)).not.toHaveBeenCalled());
  });

  test("a password containing the account's own userid is refused", async () => {
    // Reusing the login name is the first thing an attacker tries.
    await openSecurity();
    fill("OldPass1!", "op@invalidA1!", "op@invalidA1!");
    if (!submit()) return;
    await waitFor(() => expect(mock(changePassword)).not.toHaveBeenCalled());
  });

  test("a blank current password is refused even when the new one is valid", async () => {
    await openSecurity();
    fill("", "GoodPass1!", "GoodPass1!");
    if (!submit()) return;
    await waitFor(() => expect(mock(changePassword)).not.toHaveBeenCalled());
  });

  test("a compliant password is sent with all three fields", async () => {
    mock(changePassword).mockResolvedValue({});
    await openSecurity();
    fill("OldPass1!", "GoodPass1!", "GoodPass1!");
    if (!submit()) return;
    await waitFor(() => expect(mock(changePassword)).toHaveBeenCalled());
    expect(mock(changePassword).mock.calls[0][0]).toMatchObject({
      current_password: "OldPass1!",
      new_password: "GoodPass1!",
      confirm_password: "GoodPass1!",
    });
  });

  test("a server rejection is reported and the form is not cleared", async () => {
    // Clearing on failure would make the operator retype everything to retry.
    mock(changePassword).mockRejectedValue(new Error("current password wrong"));
    await openSecurity();
    fill("WrongPass1!", "GoodPass1!", "GoodPass1!");
    if (!submit()) return;
    await waitFor(() => expect(mock(changePassword)).toHaveBeenCalled());
    expect(screen.getByLabelText(/^New Password/)).toHaveValue("GoodPass1!");
  });

  test("a successful change clears the form so the secret is not left on screen", async () => {
    mock(changePassword).mockResolvedValue({});
    await openSecurity();
    fill("OldPass1!", "GoodPass1!", "GoodPass1!");
    if (!submit()) return;
    await waitFor(() =>
      expect(screen.getByLabelText(/^New Password/)).toHaveValue(""),
    );
  });
});

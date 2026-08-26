// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- see UserDetail.test.tsx.
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

vi.mock("../../Services/api", () => ({
  default: { post: vi.fn() },
}));

import axiosInstance from "../../Services/api";
import AddHostAccountModal from "../../Components/AddHostAccountModal";

const props = (over: Record<string, unknown> = {}) => ({
  open: true,
  onClose: vi.fn(),
  hostId: "h1",
  hostPlatform: "Linux",
  onSuccess: vi.fn(),
  ...over,
});

const typeUsername = (v: string) =>
  fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: v } });

const create = () =>
  fireEvent.click(screen.getByRole("button", { name: "Create User" }));

describe("AddHostAccountModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(axiosInstance.post).mockResolvedValue({ data: {} });
  });

  afterEach(() => vi.restoreAllMocks());

  test("renders nothing while closed", () => {
    render(<AddHostAccountModal {...props({ open: false })} />);
    expect(screen.queryByText("Add User Account")).not.toBeInTheDocument();
  });

  test("shows the unix description on a Linux host", () => {
    render(<AddHostAccountModal {...props()} />);
    expect(
      screen.getByText("Create a new user account on this host."),
    ).toBeInTheDocument();
  });

  test("shows the Windows description on a Windows host", () => {
    render(<AddHostAccountModal {...props({ hostPlatform: "Windows" })} />);
    expect(
      screen.getByText(
        "Create a new local user account on this Windows host.",
      ),
    ).toBeInTheDocument();
  });

  test("create is disabled until a username is typed", async () => {
    render(<AddHostAccountModal {...props()} />);
    // The empty case is guarded by disabling the control, so the validator's
    // "Username is required" branch is unreachable from the UI.
    expect(screen.getByRole("button", { name: "Create User" })).toBeDisabled();
    typeUsername("ana");
    expect(
      screen.getByRole("button", { name: "Create User" }),
    ).not.toBeDisabled();
  });

  test("a username starting with a digit is refused", async () => {
    render(<AddHostAccountModal {...props()} />);
    typeUsername("1bad");
    create();
    expect(
      await screen.findByText(
        "Username must start with a letter and contain only letters, numbers, underscores, and dashes",
      ),
    ).toBeInTheDocument();
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });

  test("a username with a space is refused", async () => {
    render(<AddHostAccountModal {...props()} />);
    typeUsername("bad name");
    create();
    expect(
      await screen.findByText(
        "Username must start with a letter and contain only letters, numbers, underscores, and dashes",
      ),
    ).toBeInTheDocument();
  });

  test("underscores and dashes are accepted", async () => {
    render(<AddHostAccountModal {...props()} />);
    typeUsername("ok_name-2");
    create();
    await waitFor(() =>
      expect(axiosInstance.post).toHaveBeenCalledWith(
        "/api/v1/host/h1/accounts",
        expect.objectContaining({ username: "ok_name-2" }),
      ),
    );
  });

  test("a username padded with whitespace is rejected, not silently trimmed", async () => {
    render(<AddHostAccountModal {...props()} />);
    typeUsername("  spaced  ");
    create();
    // The pattern rule runs against the RAW value while the payload builder
    // trims, so padding is reported rather than quietly accepted -- the user
    // finds out now instead of getting a subtly different account name.
    expect(
      await screen.findByText(
        "Username must start with a letter and contain only letters, numbers, underscores, and dashes",
      ),
    ).toBeInTheDocument();
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });

  test("a successful create notifies the caller and closes", async () => {
    const p = props();
    render(<AddHostAccountModal {...p} />);
    typeUsername("ana");
    create();
    await waitFor(() => expect(p.onSuccess).toHaveBeenCalled());
    expect(p.onClose).toHaveBeenCalled();
  });

  test("surfaces the server's detail when the create is refused", async () => {
    vi.mocked(axiosInstance.post).mockRejectedValue({
      response: { data: { detail: "user already exists" } },
    });
    render(<AddHostAccountModal {...props()} />);
    typeUsername("ana");
    create();
    expect(await screen.findByText("user already exists")).toBeInTheDocument();
  });

  test("falls back to the error message when there is no detail", async () => {
    vi.mocked(axiosInstance.post).mockRejectedValue(new Error("network down"));
    render(<AddHostAccountModal {...props()} />);
    typeUsername("ana");
    create();
    expect(await screen.findByText("network down")).toBeInTheDocument();
  });

  test("a failed create leaves the dialog open", async () => {
    const p = props();
    vi.mocked(axiosInstance.post).mockRejectedValue(new Error("nope"));
    render(<AddHostAccountModal {...p} />);
    typeUsername("ana");
    create();
    await screen.findByText("nope");
    expect(p.onSuccess).not.toHaveBeenCalled();
    expect(p.onClose).not.toHaveBeenCalled();
  });

  test("cancel closes without sending anything", () => {
    const p = props();
    render(<AddHostAccountModal {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(p.onClose).toHaveBeenCalled();
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });

  test("a non-numeric UID disables create", async () => {
    render(<AddHostAccountModal {...props()} />);
    typeUsername("ana");
    fireEvent.change(screen.getByLabelText(/^User ID \(UID\)/), {
      target: { value: "abc" },
    });
    expect(screen.getByRole("button", { name: "Create User" })).toBeDisabled();
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });
});

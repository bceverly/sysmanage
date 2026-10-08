// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/api", () => ({
  default: { post: vi.fn() },
}));

import axiosInstance from "../../Services/api";
import AddHostGroupModal from "../../Components/AddHostGroupModal";

const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;

const nameField = () => screen.getByRole("textbox", { name: /Group Name/ });
const createButton = () => screen.getByRole("button", { name: "Create Group" });

const renderModal = (platform = "Linux", extra: Record<string, unknown> = {}) => {
  const onClose = vi.fn();
  const onSuccess = vi.fn();
  render(
    <AddHostGroupModal
      open
      onClose={onClose}
      hostId="h1"
      hostPlatform={platform}
      onSuccess={onSuccess}
      {...extra}
    />,
  );
  return { onClose, onSuccess };
};

describe("AddHostGroupModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPost.mockResolvedValue({ data: {} });
  });

  test("unix host shows the GID field and no description", () => {
    renderModal("Linux");
    expect(screen.getByText("Create a new group on this host.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Group ID/ })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /Description/ })).toBeNull();
    expect(createButton()).toBeDisabled();
  });

  test("windows host shows the description field and no GID", () => {
    renderModal("Windows Server 2022");
    expect(
      screen.getByText("Create a new local group on this Windows host."),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Description/ })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /Group ID/ })).toBeNull();
  });

  test("lowercases the name and posts a unix group with a GID", async () => {
    const { onClose, onSuccess } = renderModal("Linux");
    fireEvent.change(nameField(), { target: { value: "DevOps" } });
    expect(nameField()).toHaveValue("devops");
    fireEvent.change(screen.getByRole("textbox", { name: /Group ID/ }), {
      target: { value: "2001" },
    });
    fireEvent.click(createButton());
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/v1/host/h1/groups", {
        group_name: "devops",
        gid: 2001,
      }),
    );
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  test("posts a windows group with a trimmed description", async () => {
    renderModal("windows");
    fireEvent.change(nameField(), { target: { value: "admins" } });
    fireEvent.change(screen.getByRole("textbox", { name: /Description/ }), {
      target: { value: "  ops team  " },
    });
    fireEvent.click(createButton());
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/v1/host/h1/groups", {
        group_name: "admins",
        description: "ops team",
      }),
    );
  });

  test("works without an onSuccess callback", async () => {
    const onClose = vi.fn();
    render(
      <AddHostGroupModal open onClose={onClose} hostId="h2" hostPlatform="Linux" />,
    );
    fireEvent.change(nameField(), { target: { value: "staff" } });
    fireEvent.click(createButton());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(mockPost).toHaveBeenCalledWith("/api/v1/host/h2/groups", {
      group_name: "staff",
    });
  });

  test("flags a GID below 1000 and keeps create disabled", () => {
    renderModal("Linux");
    fireEvent.change(nameField(), { target: { value: "staff" } });
    fireEvent.change(screen.getByRole("textbox", { name: /Group ID/ }), {
      target: { value: "50" },
    });
    expect(screen.getByText("GID must be a number >= 1000")).toBeInTheDocument();
    expect(createButton()).toBeDisabled();
  });

  test("rejects a name that does not start with a letter", async () => {
    renderModal("Linux");
    fireEvent.change(nameField(), { target: { value: "1bad" } });
    fireEvent.click(createButton());
    expect(
      await screen.findByText(
        "Group name must start with a letter and contain only letters, numbers, underscores, and dashes",
      ),
    ).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  test("a whitespace-only name keeps create disabled", () => {
    renderModal("Linux");
    fireEvent.change(nameField(), { target: { value: "   " } });
    expect(createButton()).toBeDisabled();
  });

  test("shows the server detail on failure", async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: "group exists" } } });
    const { onClose } = renderModal("Linux");
    fireEvent.change(nameField(), { target: { value: "staff" } });
    fireEvent.click(createButton());
    expect(await screen.findByText("group exists")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  test("shows a generic message when the response has no detail", async () => {
    mockPost.mockRejectedValue({ response: { data: {} } });
    renderModal("Linux");
    fireEvent.change(nameField(), { target: { value: "staff" } });
    fireEvent.click(createButton());
    expect(await screen.findByText("Failed to create group")).toBeInTheDocument();
  });

  test("shows an Error's message on a non-axios failure", async () => {
    mockPost.mockRejectedValue(new Error("socket closed"));
    renderModal("Linux");
    fireEvent.change(nameField(), { target: { value: "staff" } });
    fireEvent.click(createButton());
    expect(await screen.findByText("socket closed")).toBeInTheDocument();
  });

  test("cancel closes the dialog", () => {
    const { onClose } = renderModal("Linux");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });

  test("cancel is ignored while a submit is in flight", async () => {
    let resolve: (_v: unknown) => void = () => {};
    mockPost.mockReturnValue(new Promise((r) => { resolve = r; }));
    const { onClose } = renderModal("Linux");
    fireEvent.change(nameField(), { target: { value: "staff" } });
    fireEvent.click(createButton());
    const cancel = screen.getByRole("button", { name: "Cancel" });
    await waitFor(() => expect(cancel).toBeDisabled());
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    resolve({ data: {} });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });
});

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
vi.mock("react-router", () => ({ useNavigate: () => mockNavigate }));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn() },
}));

import api from "../../Services/api";
import AuditLogViewer from "../../Pages/AuditLogViewer";

const entry = (over: Record<string, unknown> = {}) => ({
  id: "e1",
  timestamp: "2026-08-01T10:00:00Z",
  username: "ana@invalid",
  action_type: "UPDATE",
  entity_type: "host",
  entity_id: "h1",
  entity_name: "alpha.invalid",
  description: "changed the tag",
  category: "inventory",
  entry_type: "user",
  ip_address: "10.0.0.1",
  user_agent: "curl",
  result: "SUCCESS",
  error_message: null,
  ...over,
});

const listOk = (entries: unknown[] = [entry()], total = 1) =>
  vi.mocked(api.get).mockResolvedValue({ data: { entries, total } });

describe("AuditLogViewer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listOk();
  });

  afterEach(() => vi.restoreAllMocks());

  test("lists entries returned by the server", async () => {
    render(<AuditLogViewer />);
    expect(await screen.findByText("ana@invalid")).toBeInTheDocument();
    expect(screen.getByText("changed the tag")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(
      "/api/v1/audit-log/list",
      expect.anything(),
    );
  });

  test("survives a failed fetch without blanking the page", async () => {
    vi.mocked(api.get).mockRejectedValue(new Error("down"));
    render(<AuditLogViewer />);
    expect(await screen.findByText("Audit Log")).toBeInTheDocument();
  });

  test("a search term is passed through as a request parameter", async () => {
    render(<AuditLogViewer />);
    await screen.findByText("ana@invalid");
    vi.mocked(api.get).mockClear();
    listOk();
    fireEvent.change(
      screen.getByLabelText(/^Search \(description or entity name\)/),
      { target: { value: "tag" } },
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        "/api/v1/audit-log/list",
        expect.objectContaining({
          params: expect.objectContaining({ search: "tag" }),
        }),
      ),
    );
  });

  test("reset clears the filters and re-queries", async () => {
    render(<AuditLogViewer />);
    await screen.findByText("ana@invalid");
    const search = screen.getByLabelText(
      /^Search \(description or entity name\)/,
    );
    fireEvent.change(search, { target: { value: "tag" } });
    await waitFor(() => expect(search).toHaveValue("tag"));
    fireEvent.click(screen.getByRole("button", { name: /Reset/ }));
    await waitFor(() => expect(search).toHaveValue(""));
  });

  test("refresh re-reads the list", async () => {
    render(<AuditLogViewer />);
    await screen.findByText("ana@invalid");
    vi.mocked(api.get).mockClear();
    listOk();
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(api.get).toHaveBeenCalled());
  });

  test("exporting CSV requests a blob and offers a download", async () => {
    const createObjectURL = vi.fn(() => "blob:x");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(globalThis.HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);

    render(<AuditLogViewer />);
    await screen.findByText("ana@invalid");
    vi.mocked(api.get).mockResolvedValue({ data: new globalThis.Blob(["a,b"]) });
    fireEvent.click(screen.getByRole("button", { name: /Export CSV/ }));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        "/api/v1/audit-log/export",
        expect.objectContaining({
          responseType: "blob",
          params: expect.objectContaining({ fmt: "csv" }),
        }),
      ),
    );
    expect(click).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  test("exporting PDF asks for the pdf format", async () => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:x"),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(globalThis.HTMLAnchorElement.prototype, "click").mockImplementation(
      () => undefined,
    );
    render(<AuditLogViewer />);
    await screen.findByText("ana@invalid");
    vi.mocked(api.get).mockResolvedValue({ data: new globalThis.Blob(["%PDF"]) });
    fireEvent.click(screen.getByRole("button", { name: /Export PDF/ }));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        "/api/v1/audit-log/export",
        expect.objectContaining({
          params: expect.objectContaining({ fmt: "pdf" }),
        }),
      ),
    );
    vi.unstubAllGlobals();
  });

  test("a 402 on export tells the user it needs a licence", async () => {
    const alertSpy = vi
      .spyOn(globalThis, "alert")
      .mockImplementation(() => undefined);
    render(<AuditLogViewer />);
    await screen.findByText("ana@invalid");
    vi.mocked(api.get).mockRejectedValue({ response: { status: 402 } });
    fireEvent.click(screen.getByRole("button", { name: /Export CSV/ }));
    await waitFor(() =>
      expect(alertSpy).toHaveBeenCalledWith(
        "Audit log export requires a SysManage Professional+ license.",
      ),
    );
  });

  test("the back button navigates away", async () => {
    render(<AuditLogViewer />);
    await screen.findByText("ana@invalid");
    fireEvent.click(screen.getByRole("button", { name: /Back/ }));
    expect(mockNavigate).toHaveBeenCalled();
  });

  test("an empty result set still renders the table headings", async () => {
    listOk([], 0);
    render(<AuditLogViewer />);
    expect(await screen.findByText("Timestamp")).toBeInTheDocument();
    expect(screen.getByText("Username")).toBeInTheDocument();
  });
});

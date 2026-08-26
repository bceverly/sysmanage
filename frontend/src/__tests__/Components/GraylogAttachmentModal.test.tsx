// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- the loader lists `t` in its deps.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/api", () => ({ default: { get: vi.fn() } }));

vi.mock("../../Services/graylog", () => ({
  doCheckGraylogHealth: vi.fn(),
  doAttachToGraylog: vi.fn(),
}));

import axiosInstance from "../../Services/api";
import {
  doCheckGraylogHealth,
  doAttachToGraylog,
} from "../../Services/graylog";
import GraylogAttachmentModal from "../../Components/GraylogAttachmentModal";

const health = (over: Record<string, unknown> = {}) => ({
  healthy: true,
  has_windows_sidecar: true,
  windows_sidecar_port: 9000,
  has_syslog_tcp: true,
  syslog_tcp_port: 514,
  has_syslog_udp: true,
  syslog_udp_port: 514,
  has_gelf_tcp: true,
  gelf_tcp_port: 12201,
  ...over,
});

const props = (over: Record<string, unknown> = {}) => ({
  open: true,
  onClose: vi.fn(),
  hostId: "h1",
  hostPlatform: "Linux",
  ...over,
});

describe("GraylogAttachmentModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(doCheckGraylogHealth).mockResolvedValue(health() as never);
    vi.mocked(doAttachToGraylog).mockResolvedValue(undefined as never);
    vi.mocked(axiosInstance.get).mockResolvedValue({
      data: { use_managed_server: true, host: { ipv4: "10.0.0.5" } },
    });
    vi.spyOn(globalThis.console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  test("renders the mechanism prompt once loaded", async () => {
    render(<GraylogAttachmentModal {...props()} />);
    expect(
      await screen.findByText(
        "Select the log forwarding mechanism to use:",
      ),
    ).toBeInTheDocument();
  });

  test("an unhealthy server is reported instead of offering mechanisms", async () => {
    vi.mocked(doCheckGraylogHealth).mockResolvedValue(
      health({ healthy: false }) as never,
    );
    render(<GraylogAttachmentModal {...props()} />);
    expect(
      await screen.findByText(
        "Graylog server is not healthy or not configured",
      ),
    ).toBeInTheDocument();
    expect(axiosInstance.get).not.toHaveBeenCalled();
  });

  test("a failed health check is reported", async () => {
    vi.mocked(doCheckGraylogHealth).mockRejectedValue(new Error("down"));
    render(<GraylogAttachmentModal {...props()} />);
    expect(
      await screen.findByText("Failed to load Graylog settings"),
    ).toBeInTheDocument();
  });

  test("a platform with no compatible mechanism says so", async () => {
    vi.mocked(doCheckGraylogHealth).mockResolvedValue(
      health({
        has_windows_sidecar: false,
        has_syslog_tcp: false,
        has_syslog_udp: false,
        has_gelf_tcp: false,
      }) as never,
    );
    render(<GraylogAttachmentModal {...props()} />);
    expect(
      await screen.findByText(
        "No compatible log forwarding mechanisms are available for this platform",
      ),
    ).toBeInTheDocument();
  });

  test("the first available mechanism is preselected so apply is ready", async () => {
    render(<GraylogAttachmentModal {...props()} />);
    await screen.findByText("Select the log forwarding mechanism to use:");
    // The loader preselects options[0], which is why handleSubmit's "select a
    // mechanism" branch and the disabled-apply state are both unreachable
    // whenever at least one mechanism exists.
    expect(screen.getByRole("radio", { name: /Syslog TCP/ })).toBeChecked();
    expect(screen.getByRole("button", { name: "Apply" })).not.toBeDisabled();
  });

  test("apply is disabled when no mechanism is available at all", async () => {
    vi.mocked(doCheckGraylogHealth).mockResolvedValue(
      health({
        has_windows_sidecar: false,
        has_syslog_tcp: false,
        has_syslog_udp: false,
        has_gelf_tcp: false,
      }) as never,
    );
    render(<GraylogAttachmentModal {...props()} />);
    await screen.findByText(
      "No compatible log forwarding mechanisms are available for this platform",
    );
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  test("selecting a mechanism and applying sends it with its port", async () => {
    render(<GraylogAttachmentModal {...props()} />);
    await screen.findByText("Select the log forwarding mechanism to use:");
    fireEvent.click(screen.getByRole("radio", { name: /Syslog TCP/ }));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() =>
      expect(doAttachToGraylog).toHaveBeenCalledWith("h1", {
        mechanism: "syslog_tcp",
        graylog_server: "10.0.0.5",
        port: 514,
      }),
    );
  });

  test("a successful attach closes the modal", async () => {
    const p = props();
    render(<GraylogAttachmentModal {...p} />);
    await screen.findByText("Select the log forwarding mechanism to use:");
    fireEvent.click(screen.getByRole("radio", { name: /Syslog TCP/ }));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(p.onClose).toHaveBeenCalled());
  });

  test("surfaces the server's detail when the attach is refused", async () => {
    vi.mocked(doAttachToGraylog).mockRejectedValue({
      response: { data: { detail: "agent offline" } },
    });
    render(<GraylogAttachmentModal {...props()} />);
    await screen.findByText("Select the log forwarding mechanism to use:");
    fireEvent.click(screen.getByRole("radio", { name: /Syslog TCP/ }));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("agent offline")).toBeInTheDocument();
  });

  test("falls back to a generic message when the failure has no detail", async () => {
    vi.mocked(doAttachToGraylog).mockRejectedValue(new Error("boom"));
    render(<GraylogAttachmentModal {...props()} />);
    await screen.findByText("Select the log forwarding mechanism to use:");
    fireEvent.click(screen.getByRole("radio", { name: /Syslog TCP/ }));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(
      await screen.findByText("Failed to attach to Graylog"),
    ).toBeInTheDocument();
  });

  test("cancel closes without attaching", async () => {
    const p = props();
    render(<GraylogAttachmentModal {...p} />);
    await screen.findByText("Select the log forwarding mechanism to use:");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(p.onClose).toHaveBeenCalled();
    expect(doAttachToGraylog).not.toHaveBeenCalled();
  });
});

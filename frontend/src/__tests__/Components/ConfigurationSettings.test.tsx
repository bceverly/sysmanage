// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

// Stable `t`: the component's load callback depends on it.
vi.mock("react-i18next", () => {
  const value = {
    t: (k: string, f?: string) => f || k,
    i18n: { language: "en" },
  };
  return { useTranslation: () => value };
});

vi.mock("../../Services/serverSettings", () => ({
  serverSettingsService: { get: vi.fn(), update: vi.fn() },
}));

vi.mock("../../Components/SendTestEmailButton", () => ({
  default: () => <div data-testid="send-test-email" />,
}));

import { serverSettingsService } from "../../Services/serverSettings";
import ConfigurationSettings from "../../Components/ConfigurationSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const settings = [
  { key: "heartbeat_timeout", group: "monitoring", type: "int", value: 5 },
  { key: "cookie_domain", group: "security", type: "str", value: "example.com" },
  { key: "email_enabled", group: "email", type: "bool", value: false },
  {
    key: "email_password",
    group: "email",
    type: "secret",
    value: "",
    configured: true,
  },
  {
    key: "custom_secret",
    group: "email",
    type: "secret",
    value: "",
    configured: false,
  },
  { key: "unknown_field", group: "message_queue", type: "str", value: "x" },
  { key: "ignored", group: "not_in_order", type: "str", value: "y" },
];

beforeEach(() => {
  vi.clearAllMocks();
  m(serverSettingsService.get).mockResolvedValue(settings);
  m(serverSettingsService.update).mockImplementation(
    async (v: Record<string, unknown>) =>
      settings.map((s) => ({ ...s, value: v[s.key] ?? s.value })),
  );
});

test("renders grouped settings with labels in group order", async () => {
  render(<ConfigurationSettings />);
  expect(await screen.findByText("Configuration")).toBeInTheDocument();
  expect(screen.getByText("Security & Sessions")).toBeInTheDocument();
  expect(screen.getByText("Monitoring")).toBeInTheDocument();
  expect(screen.getByText("Message Queue")).toBeInTheDocument();
  expect(screen.getByText("Email")).toBeInTheDocument();
  // Groups not in GROUP_ORDER are skipped.
  expect(screen.queryByLabelText("ignored")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Heartbeat timeout (minutes)")).toHaveValue(5);
  expect(screen.getByLabelText("Cookie domain (blank = host only)")).toHaveValue(
    "example.com",
  );
  // Unknown keys fall back to the raw key as label.
  expect(screen.getByLabelText("unknown_field")).toHaveValue("x");
  expect(screen.getByTestId("send-test-email")).toBeInTheDocument();
  // Secret helper text differs by configured state.
  expect(
    screen.getByText(
      "A password is stored in OpenBAO. Type a new one to replace it.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Stored securely in OpenBAO, not in the database."),
  ).toBeInTheDocument();
  expect(screen.getByPlaceholderText("Not set")).toBeInTheDocument();
});

test("edits every field type and saves the values", async () => {
  render(<ConfigurationSettings />);
  const hb = await screen.findByLabelText("Heartbeat timeout (minutes)");
  fireEvent.change(hb, { target: { value: "12" } });
  fireEvent.change(screen.getByLabelText("Cookie domain (blank = host only)"), {
    target: { value: "corp.local" },
  });
  fireEvent.click(screen.getByLabelText("Email enabled"));
  fireEvent.change(screen.getByLabelText("SMTP password"), {
    target: { value: "s3cret" },
  });

  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() =>
    expect(serverSettingsService.update).toHaveBeenCalledWith(
      expect.objectContaining({
        heartbeat_timeout: 12,
        cookie_domain: "corp.local",
        email_enabled: true,
        email_password: "s3cret",
      }),
    ),
  );
  expect(await screen.findByText("Configuration saved.")).toBeInTheDocument();
});

test("shows a save error and lets the user dismiss it", async () => {
  m(serverSettingsService.update).mockRejectedValue(new Error("boom"));
  render(<ConfigurationSettings />);
  await screen.findByText("Configuration");
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(
    await screen.findByText("Failed to save configuration settings."),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /close/i }));
  await waitFor(() =>
    expect(
      screen.queryByText("Failed to save configuration settings."),
    ).not.toBeInTheDocument(),
  );
});

test("shows a load error when settings cannot be fetched", async () => {
  m(serverSettingsService.get).mockRejectedValue(new Error("nope"));
  render(<ConfigurationSettings />);
  expect(
    await screen.findByText("Failed to load configuration settings."),
  ).toBeInTheDocument();
  expect(screen.queryByText("Monitoring")).not.toBeInTheDocument();
});

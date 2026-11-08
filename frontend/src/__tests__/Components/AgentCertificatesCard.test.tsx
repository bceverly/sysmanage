// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Agent certificates card (ROADMAP 25.10): shows the mode and who is not
// ready, and asks before enforcing when the server says hosts would be cut off.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const value = {
    t: (k: string, f?: string | Record<string, unknown>) => (typeof f === "string" ? f : k),
    i18n: { language: "en" },
  };
  return { useTranslation: () => value };
});

vi.mock("../../Services/agentCertificates", () => ({
  agentCertificatesService: { get: vi.fn(), setMode: vi.fn() },
}));

import { agentCertificatesService } from "../../Services/agentCertificates";
import type { AgentCertificateSettings } from "../../Services/agentCertificates";
import AgentCertificatesCard from "../../Components/AgentCertificatesCard";

const SETTINGS: AgentCertificateSettings = {
  mode: "optional",
  modes: ["off", "optional", "enforced"],
  fleet: {
    approved: 3, presenting: 2, not_presenting: 1, expiring: 0, expired: 0,
    not_ready: [{ id: "h3", fqdn: "old-agent.example.com", status: "none" }],
  },
};

beforeEach(() => {
  vi.mocked(agentCertificatesService.get).mockResolvedValue(SETTINGS);
  vi.mocked(agentCertificatesService.setMode).mockReset();
});

const chooseEnforced = async () => {
  fireEvent.mouseDown(await screen.findByRole("combobox"));
  fireEvent.click(within(await screen.findByRole("listbox")).getByText("Enforced"));
};

test("shows the mode and the hosts that are not ready", async () => {
  render(<AgentCertificatesCard />);
  expect(await screen.findByText("old-agent.example.com")).toBeInTheDocument();
  expect(screen.getByRole("combobox")).toHaveTextContent("Optional");
});

test("asks before enforcing when hosts are not presenting, then enforces", async () => {
  vi.mocked(agentCertificatesService.setMode)
    .mockRejectedValueOnce({
      response: { status: 409, data: { detail: {
        code: "hosts_not_presenting", count: 1, message: "1 approved host(s) have not presented",
      } } },
    })
    .mockResolvedValueOnce({ ...SETTINGS, mode: "enforced" });
  render(<AgentCertificatesCard />);
  await chooseEnforced();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("1 approved host(s) have not presented")).toBeInTheDocument();
  expect(agentCertificatesService.setMode).toHaveBeenLastCalledWith("enforced", false);
  fireEvent.click(screen.getByRole("button", { name: "Enforce anyway" }));
  await waitFor(() =>
    expect(agentCertificatesService.setMode).toHaveBeenLastCalledWith("enforced", true));
});

test("a failed save says so", async () => {
  vi.mocked(agentCertificatesService.setMode).mockRejectedValueOnce(new Error("down"));
  render(<AgentCertificatesCard />);
  await chooseEnforced();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Could not save the agent certificate setting.")).toBeInTheDocument();
});

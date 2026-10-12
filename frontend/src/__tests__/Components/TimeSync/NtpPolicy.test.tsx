// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("./_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { MANAGE_TIME_SYNC: "Manage Time Sync" },
}));
vi.mock("../../../Services/timeSync", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/timeSync")>();
  return { ...actual, getNtpPolicies: vi.fn(), setNtpPolicy: vi.fn(), clearNtpPolicy: vi.fn() };
});

import { hasPermission } from "../../../Services/permissions";
import { clearNtpPolicy, getNtpPolicies, setNtpPolicy } from "../../../Services/timeSync";
import type { HostNtpPolicy, NtpPolicy } from "../../../Services/timeSync";
import NtpPolicySettings from "../../../Components/TimeSync/NtpPolicySettings";
import HostClockPolicy from "../../../Components/TimeSync/HostClockPolicy";

const POLICY: NtpPolicy = {
  id: "p1",
  scope_kind: "tag",
  scope_ref: "t1",
  servers: ["ntp1.lab", "ntp2.lab"],
  enforce: true,
  auto_resync: true,
  updated_at: null,
  updated_by: null,
};

describe("NtpPolicySettings", () => {
  beforeEach(() => {
    vi.mocked(hasPermission).mockResolvedValue(true);
    vi.mocked(getNtpPolicies).mockResolvedValue({ policies: [POLICY], max_servers: 8 });
  });

  test("lists policies by target and saves a new one", async () => {
    vi.mocked(setNtpPolicy).mockResolvedValue({ ...POLICY, scope_kind: "fleet", scope_ref: "" });
    render(<NtpPolicySettings tags={[{ id: "t1", name: "domain-controllers" }]} sites={[]} />);
    expect(await screen.findByText("Tag: domain-controllers")).toBeInTheDocument();
    expect(screen.getByText("ntp1.lab, ntp2.lab")).toBeInTheDocument();
    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByText("Auto-resync")).toBeInTheDocument();
    const field = screen.getByLabelText("NTP servers");
    await waitFor(() => expect(field).not.toBeDisabled());
    fireEvent.change(field, { target: { value: "10.0.0.1, 10.0.0.2" } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() =>
      expect(setNtpPolicy).toHaveBeenCalledWith({
        scope_kind: "fleet",
        scope_ref: "",
        servers: ["10.0.0.1", "10.0.0.2"],
        enforce: false,
        auto_resync: false,
      }),
    );
  });

  test("a refused policy says why", async () => {
    vi.mocked(setNtpPolicy).mockRejectedValue({
      response: { data: { detail: { code: "bad_server" } } },
    });
    render(<NtpPolicySettings tags={[]} sites={[]} />);
    const field = await screen.findByLabelText("NTP servers");
    await waitFor(() => expect(field).not.toBeDisabled());
    fireEvent.change(field, { target: { value: "x" } });
    fireEvent.click(screen.getByText("Save"));
    expect(
      await screen.findByText("Each server must be a host name or an IP address."),
    ).toBeInTheDocument();
  });

  test("removes a policy", async () => {
    vi.mocked(clearNtpPolicy).mockResolvedValue();
    render(<NtpPolicySettings tags={[]} sites={[]} />);
    const button = await screen.findByLabelText("Remove policy");
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);
    await waitFor(() => expect(clearNtpPolicy).toHaveBeenCalledWith("tag", "t1"));
  });
});

const VERDICT: HostNtpPolicy = {
  policy: POLICY,
  conflict: false,
  findings: [{ code: "servers_differ" }, { code: "not_enabled" }],
  compliant: false,
  apply_status: "failed",
  apply_error: "chronyd: unit not found",
  configured_servers: ["pool.ntp.org"],
  enabled: false,
};

describe("HostClockPolicy", () => {
  test("shows the policy, what the host has, and why applying failed", () => {
    render(<HostClockPolicy verdict={VERDICT} />);
    expect(screen.getByText("2 differences")).toBeInTheDocument();
    expect(screen.getByText("Policy servers: ntp1.lab, ntp2.lab")).toBeInTheDocument();
    expect(screen.getByText("Configured on the host: pool.ntp.org")).toBeInTheDocument();
    expect(screen.getByText("- Uses other NTP servers than the policy")).toBeInTheDocument();
    expect(screen.getByText("chronyd: unit not found")).toBeInTheDocument();
  });

  test("nothing without a policy or the engine", () => {
    const { container } = render(<HostClockPolicy verdict={null} />);
    expect(container).toBeEmptyDOMElement();
    const none = render(
      <HostClockPolicy verdict={{ ...VERDICT, policy: null, compliant: null, findings: [] }} />,
    );
    expect(none.container).toBeEmptyDOMElement();
  });

  test("a compliant host says so", () => {
    render(<HostClockPolicy verdict={{ ...VERDICT, compliant: true, findings: [], apply_status: "succeeded", apply_error: null }} />);
    expect(screen.getByText("Follows the policy")).toBeInTheDocument();
    expect(screen.getByText("The policy was applied.")).toBeInTheDocument();
  });
});

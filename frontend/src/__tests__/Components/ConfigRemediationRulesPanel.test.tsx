// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Remediation playbook rules.
 *
 * The rule that matters most here is about ORDER. Rules are listed in
 * precedence order, not alphabetically, because the list IS the sequence a
 * finding is tested against -- and an operator who cannot predict which repair
 * fires will never switch an automatic one on.
 *
 * Automatic repair is also the largest blast radius in this feature, so it is
 * visibly labeled and off by default.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
  let s = typeof fallback === "string" ? fallback : key;
  if (opts) {
    for (const [k, v] of Object.entries(opts)) {
      s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
    }
  }
  return s;
};
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("../../Services/configFleetService", () => ({
  getRemediationRules: vi.fn(),
  createRemediationRule: vi.fn(),
  updateRemediationRule: vi.fn(),
  deleteRemediationRule: vi.fn(),
}));
vi.mock("../../Services/configManagementService", () => ({
  getConfigProfiles: vi.fn(),
}));

import {
  getRemediationRules,
  createRemediationRule,
  updateRemediationRule,
} from "../../Services/configFleetService";
import { getConfigProfiles } from "../../Services/configManagementService";
import ConfigRemediationRulesPanel from "../../Components/ConfigRemediationRulesPanel";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const rule = (over = {}) => ({
  id: "r1",
  name: "sshd repair",
  description: null,
  profile_id: null,
  profile_name: null,
  task_pattern: "ensure sshd*",
  remediation_profile_id: "p2",
  remediation_profile_name: "sshd fix",
  enabled: true,
  priority: 100,
  auto_apply: false,
  created_by: "op",
  updated_by: "op",
  created_at: null,
  updated_at: null,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  m(getRemediationRules).mockResolvedValue([rule()]);
  m(getConfigProfiles).mockResolvedValue([
    { id: "p2", name: "sshd fix", engine: "ansible-core", content: "", version: 1,
      is_active: true, description: null, created_by: null, updated_by: null,
      created_at: null, updated_at: null },
  ]);
});

describe("ConfigRemediationRulesPanel", () => {
  test("a rule shows what it matches and what repairs it", async () => {
    render(<ConfigRemediationRulesPanel canEdit />);
    expect(await screen.findByText("ensure sshd*")).toBeInTheDocument();
    expect(screen.getByText(/sshd fix/)).toBeInTheDocument();
  });

  test("precedence is visible, because the list is the matching order", async () => {
    render(<ConfigRemediationRulesPanel canEdit />);
    expect(await screen.findByText("Priority 100")).toBeInTheDocument();
  });

  test("an unscoped rule says it applies to drift from any profile", async () => {
    render(<ConfigRemediationRulesPanel canEdit />);
    expect(await screen.findByText("Drift from any profile")).toBeInTheDocument();
  });

  test("a scoped rule names the profile it is narrowed to", async () => {
    m(getRemediationRules).mockResolvedValue([
      rule({ profile_id: "p1", profile_name: "baseline" }),
    ]);
    render(<ConfigRemediationRulesPanel canEdit />);
    expect(await screen.findByText("Only drift from baseline")).toBeInTheDocument();
  });

  test("an automatic rule is visibly marked", async () => {
    // The largest blast radius in this feature; it should never be something
    // you have to open a dialog to discover.
    m(getRemediationRules).mockResolvedValue([rule({ auto_apply: true })]);
    render(<ConfigRemediationRulesPanel canEdit />);
    expect(await screen.findByText("Automatic")).toBeInTheDocument();
  });

  test("automatic repair can be switched on and off from the list", async () => {
    m(updateRemediationRule).mockResolvedValue(rule({ auto_apply: true }));
    render(<ConfigRemediationRulesPanel canEdit />);
    fireEvent.click(await screen.findByText("Repair automatically"));
    await waitFor(() =>
      expect(updateRemediationRule).toHaveBeenCalledWith("r1", {
        auto_apply: true,
      }),
    );
  });

  test("a new rule defaults to requiring approval", async () => {
    m(createRemediationRule).mockResolvedValue(rule());
    render(<ConfigRemediationRulesPanel canEdit />);
    fireEvent.click(await screen.findByText("New rule"));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "nginx repair" },
    });
    fireEvent.change(screen.getByLabelText("Task pattern"), {
      target: { value: "ensure nginx*" },
    });
    fireEvent.mouseDown(screen.getByLabelText("Repair with"));
    fireEvent.click(await screen.findByRole("option", { name: "sshd fix" }));
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(createRemediationRule).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "nginx repair",
          task_pattern: "ensure nginx*",
          remediation_profile_id: "p2",
          auto_apply: false,
        }),
      ),
    );
  });

  test("the server's refusal of a catch-all pattern is surfaced verbatim", async () => {
    // The engine explains WHY, and that explanation is worth more than a
    // generic "could not save".
    m(createRemediationRule).mockRejectedValue({
      response: {
        data: {
          detail:
            "a task pattern of '*' matches every finding; scope it to a profile or narrow it",
        },
      },
    });
    render(<ConfigRemediationRulesPanel canEdit />);
    fireEvent.click(await screen.findByText("New rule"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Task pattern"), {
      target: { value: "*" },
    });
    fireEvent.mouseDown(screen.getByLabelText("Repair with"));
    fireEvent.click(await screen.findByRole("option", { name: "sshd fix" }));
    fireEvent.click(screen.getByText("Save"));
    expect(
      await screen.findByText(/matches every finding/i),
    ).toBeInTheDocument();
  });

  test("an empty library explains what is lost without one", async () => {
    m(getRemediationRules).mockResolvedValue([]);
    render(<ConfigRemediationRulesPanel canEdit />);
    expect(
      await screen.findByText(/re-applying the whole profile/i),
    ).toBeInTheDocument();
  });

  test("without the edit permission the rules are read-only", async () => {
    render(<ConfigRemediationRulesPanel canEdit={false} />);
    await screen.findByText("sshd repair");
    expect(screen.queryByText("New rule")).not.toBeInTheDocument();
    expect(screen.queryByText("Repair automatically")).not.toBeInTheDocument();
  });
});

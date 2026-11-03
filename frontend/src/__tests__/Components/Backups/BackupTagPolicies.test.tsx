// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Policies by tag (Pro+ 24.6): listed with tag, priority and how many hosts
// follow each; hidden without the engine; a host's card names the rule.

import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
const licensed = vi.hoisted(() => ({ value: true }));
vi.mock("../../../hooks/useModuleLicensed", () => ({
  useModuleLicensed: () => licensed.value,
  default: () => licensed.value,
}));
vi.mock("../../../Services/backupTagPolicies", () => ({
  listTagPolicies: vi.fn(),
  listHostTags: vi.fn(),
  applyTagPolicies: vi.fn(),
  deleteTagPolicy: vi.fn(),
  createTagPolicy: vi.fn(),
  updateTagPolicy: vi.fn(),
}));

import { listHostTags, listTagPolicies } from "../../../Services/backupTagPolicies";
import BackupTagPolicies from "../../../Components/Backups/BackupTagPolicies";
import { PolicySourceLine, TagPolicyNote } from "../../../Components/Backups/PolicySource";

const ROW = {
  id: "tp1", name: "Servers nightly", tag_id: "t1", tag_name: "servers", priority: 10,
  enabled: true, settings: { keep_last: 7 }, hosts_tagged: 3, hosts_applied: 2,
  created_at: null, created_by: null, updated_at: null,
};

const mount = () =>
  render(<BackupTagPolicies canManage onChanged={vi.fn()} onNotice={vi.fn()} onError={vi.fn()} />);

describe("BackupTagPolicies", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    licensed.value = true;
    vi.mocked(listHostTags).mockResolvedValue([{ id: "t1", name: "servers" }]);
  });

  test("lists each tag policy with its tag, priority and followers", async () => {
    vi.mocked(listTagPolicies).mockResolvedValue([ROW] as never);
    mount();
    expect(await screen.findByText("Servers nightly")).toBeInTheDocument();
    expect(screen.getByText("servers")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("2 of 3 tagged")).toBeInTheDocument();
  });

  test("says what to do when there are no tags yet", async () => {
    vi.mocked(listTagPolicies).mockResolvedValue([]);
    vi.mocked(listHostTags).mockResolvedValue([]);
    mount();
    expect(await screen.findByText(/Add a tag to some hosts first/)).toBeInTheDocument();
  });

  test("is not shown without the backup engine", async () => {
    licensed.value = false;
    const { container } = mount();
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(listTagPolicies).not.toHaveBeenCalled();
  });
});

describe("PolicySource", () => {
  test("names the tag policy and its priority, or the host's own policy", () => {
    const { rerender } = render(
      <PolicySourceLine source={{ kind: "tag", name: "Servers nightly", priority: 10 }} />,
    );
    expect(screen.getByText("From tag policy Servers nightly (priority 10)")).toBeInTheDocument();
    rerender(<PolicySourceLine source={{ kind: "own" }} />);
    expect(screen.getByText("This host's own policy")).toBeInTheDocument();
  });

  test("the dialog warns that saving makes the settings the host's own", () => {
    render(<TagPolicyNote source={{ kind: "tag", name: "Servers nightly", priority: 10 }} />);
    expect(screen.getByText(/follows the tag policy Servers nightly/)).toBeInTheDocument();
  });
});

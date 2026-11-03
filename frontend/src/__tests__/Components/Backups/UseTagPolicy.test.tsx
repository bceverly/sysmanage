// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Use the tag policy" (Pro+ 24.6): offered only for a host on its own
// policy that a tag policy covers; the confirmation names the rule and the
// settings it replaces before anything changes.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, previewTagPolicyHandover: vi.fn(), handOverToTagPolicy: vi.fn() };
});

import { handOverToTagPolicy, previewTagPolicyHandover } from "../../../Services/backups";
import { UseTagPolicyButton } from "../../../Components/Backups/UseTagPolicy";

const covered = {
  kind: "own" as const,
  tag_policy_available: { id: "tp1", name: "Servers nightly", priority: 10 },
};

describe("UseTagPolicyButton", () => {
  beforeEach(() => vi.clearAllMocks());

  test("is not offered for a host already on its tag policy, or with none covering it", () => {
    const { container, rerender } = render(
      <UseTagPolicyButton hostId="h1" source={{ kind: "tag", name: "x", priority: 1 }} onDone={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(<UseTagPolicyButton hostId="h1" source={{ kind: "own" }} onDone={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("confirms the rule and the replaced settings, then hands the host over", async () => {
    vi.mocked(previewTagPolicyHandover).mockResolvedValue({
      tag_policy: { id: "tp1", name: "Servers nightly", priority: 10 },
      changes: [{ key: "keep_last", from: 30, to: 7 }],
    });
    vi.mocked(handOverToTagPolicy).mockResolvedValue({} as never);
    const onDone = vi.fn();
    render(<UseTagPolicyButton hostId="h1" source={covered} onDone={onDone} />);
    fireEvent.click(screen.getByText("Use the tag policy"));
    expect(await screen.findByText(/follow the tag policy Servers nightly \(priority 10\)/)).toBeInTheDocument();
    expect(screen.getByText("Snapshots to keep: 30 -> 7")).toBeInTheDocument();
    expect(handOverToTagPolicy).not.toHaveBeenCalled();
    const buttons = screen.getAllByText("Use the tag policy");
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(handOverToTagPolicy).toHaveBeenCalledWith("h1"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });
});

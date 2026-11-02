// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

import ScriptApprovalChip from "../../../Components/HostDetail/ScriptApprovalChip";

describe("ScriptApprovalChip", () => {
  test("says scripts need approval when the agent requires it", () => {
    render(<ScriptApprovalChip required />);
    expect(screen.getByText("Scripts need approval")).toBeInTheDocument();
  });

  test("shows nothing otherwise", () => {
    const { container } = render(<ScriptApprovalChip required={false} />);
    expect(container).toBeEmptyDOMElement();
    render(<ScriptApprovalChip />);
    expect(screen.queryByText("Scripts need approval")).not.toBeInTheDocument();
  });
});

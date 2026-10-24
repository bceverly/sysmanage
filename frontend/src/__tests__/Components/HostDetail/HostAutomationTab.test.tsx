// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The host's Automation tab: config management and its run history, plus the
 * Pro+ automation engine's panel when that plugin is licensed.  The plugin
 * registers the same ``automation`` tab id, so without the merge one of the
 * two would be lost.
 */

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";
import HostAutomationTab from "../../../Components/HostDetail/HostAutomationTab";

vi.mock("../../../Components/ConfigManagementEnginesCard", () => ({
  default: ({ hostId }: { hostId: string }) => <div data-testid="engines">{hostId}</div>,
}));
vi.mock("../../../Components/ConfigProfileRunHistory", () => ({
  default: ({ hostId }: { hostId: string }) => <div data-testid="runs">{hostId}</div>,
}));

const props = { hostId: "h-1", canInstall: true, isHostActive: true, isAgentPrivileged: true };

describe("HostAutomationTab", () => {
  test("shows config management and its run history", () => {
    render(<HostAutomationTab {...props} />);
    expect(screen.getByTestId("engines")).toHaveTextContent("h-1");
    expect(screen.getByTestId("runs")).toHaveTextContent("h-1");
  });

  test("adds the licensed plugin's panel below them", () => {
    const Plugin = ({ hostId }: { hostId: string }) => <div data-testid="plugin">{hostId}</div>;
    render(<HostAutomationTab {...props} extension={Plugin} />);
    expect(screen.getByTestId("plugin")).toHaveTextContent("h-1");
    expect(screen.getByTestId("runs")).toBeInTheDocument();
  });
});

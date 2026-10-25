// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The host's Backup tab: the Community card, plus the Pro+ backup_engine
 * panel (encryption) when that plugin is licensed -- the plugin registers the
 * same ``backup`` tab id, so the host keeps one Backup tab.
 */

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";
import HostBackupTab from "../../../Components/HostDetail/HostBackupTab";

vi.mock("../../../Components/Backups/HostBackupCard", () => ({
  default: ({ hostId }: { hostId: string }) => <div data-testid="card">{hostId}</div>,
}));

describe("HostBackupTab", () => {
  test("shows the Community card alone without the plugin", () => {
    render(<HostBackupTab hostId="h-1" />);
    expect(screen.getByTestId("card")).toHaveTextContent("h-1");
  });

  test("adds the licensed plugin's panel below it", () => {
    const Panel = ({ hostId }: { hostId: string }) => <div data-testid="panel">{hostId}</div>;
    render(<HostBackupTab hostId="h-1" extension={Panel} />);
    expect(screen.getByTestId("panel")).toHaveTextContent("h-1");
    expect(screen.getByTestId("card")).toBeInTheDocument();
  });
});

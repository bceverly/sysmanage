// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Community (no Professional+ backup engine): the Pro+ backup surfaces are
// absent, not locked teasers -- the drift timeline and its links, and the
// restore dialog's package option (ROADMAP 24.11 edition audit, 2026-11-03).

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../hooks/useModuleLicensed", () => ({
  useModuleLicensed: () => false,
  default: () => false,
}));
vi.mock("../../../Components/Backups/HostBackupCard", () => ({
  default: () => <div data-testid="community-card" />,
}));
vi.mock("../../../Components/Backups/BackupDriftTimeline", () => ({
  default: () => <div data-testid="drift-timeline" />,
}));

import HostBackupTab from "../../../Components/HostDetail/HostBackupTab";
import DriftTimelineLink from "../../../Components/Backups/DriftTimelineLink";
import RestoreFilesDialog from "../../../Components/Backups/RestoreFilesDialog";

describe("Community backups view", () => {
  test("the host's Backup tab has the card and no drift timeline", () => {
    render(<HostBackupTab hostId="h1" />);
    expect(screen.getByTestId("community-card")).toBeInTheDocument();
    expect(screen.queryByTestId("drift-timeline")).not.toBeInTheDocument();
  });

  test("no drift-timeline link from configuration drift or software history", () => {
    const { container } = render(<DriftTimelineLink hostId="h1" />);
    expect(container).toBeEmptyDOMElement();
  });

  test("the restore dialog offers no package restore", () => {
    render(<RestoreFilesDialog open hostId="h1" fqdn="t14" onClose={vi.fn()} />);
    expect(screen.queryByText(/packages back first/i)).not.toBeInTheDocument();
  });
});

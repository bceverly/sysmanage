// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Repack asks first (it reads and rewrites the whole repository on the
// storage host), then queues a "repack" run for the host.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, backupNow: vi.fn() };
});

import { backupNow } from "../../../Services/backups";
import BackupRepackButton from "../../../Components/Backups/BackupRepackButton";

describe("BackupRepackButton", () => {
  beforeEach(() => vi.clearAllMocks());

  test("asks first, then queues a repack for the host", async () => {
    const onStarted = vi.fn();
    vi.mocked(backupNow).mockResolvedValue({} as never);
    render(<BackupRepackButton hostId="h1" onStarted={onStarted} />);
    fireEvent.click(screen.getByText("Repack"));
    expect(screen.getByText("Repack this host's backups?")).toBeInTheDocument();
    expect(backupNow).not.toHaveBeenCalled();
    const buttons = screen.getAllByText("Repack");
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(backupNow).toHaveBeenCalledWith("h1", "repack"));
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
  });

  test("disabled while a job runs", () => {
    render(<BackupRepackButton hostId="h1" disabled onStarted={vi.fn()} />);
    expect(screen.getByText("Repack").closest("button")).toBeDisabled();
  });
});

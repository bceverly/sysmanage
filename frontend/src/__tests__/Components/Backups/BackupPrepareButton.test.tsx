// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Prepare storage asks first (it creates a filesystem and changes exports on
// the storage host), then queues a "prepare" run for the host; a refusal
// from the server is shown in the dialog.

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
import BackupPrepareButton from "../../../Components/Backups/BackupPrepareButton";

const confirm = () => {
  const buttons = screen.getAllByText("Prepare storage");
  fireEvent.click(buttons[buttons.length - 1]);
};

describe("BackupPrepareButton", () => {
  beforeEach(() => vi.clearAllMocks());

  test("asks first, then queues a prepare for the host", async () => {
    const onStarted = vi.fn();
    vi.mocked(backupNow).mockResolvedValue({} as never);
    render(<BackupPrepareButton hostId="h1" onStarted={onStarted} />);
    fireEvent.click(screen.getByText("Prepare storage"));
    expect(screen.getByText("Prepare the storage for this host?")).toBeInTheDocument();
    expect(backupNow).not.toHaveBeenCalled();
    confirm();
    await waitFor(() => expect(backupNow).toHaveBeenCalledWith("h1", "prepare"));
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
  });

  test("shows why the server refused", async () => {
    vi.mocked(backupNow).mockRejectedValue({ response: { data: { detail: "The backup storage host is not ready" } } });
    render(<BackupPrepareButton hostId="h1" onStarted={vi.fn()} />);
    fireEvent.click(screen.getByText("Prepare storage"));
    confirm();
    expect(await screen.findByText("The backup storage host is not ready")).toBeInTheDocument();
  });
});

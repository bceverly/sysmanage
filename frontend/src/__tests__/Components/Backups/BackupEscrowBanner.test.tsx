// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Pro+ break-glass escrow banner on the Backups page (ROADMAP 24.6,
// 2026-11-03): shown only while the export is missing or stale, and only when
// escrow applies; its button opens a host's Backup tab, where the export is.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, getEscrowStatus: vi.fn() };
});

import { getEscrowStatus } from "../../../Services/backups";
import type { EscrowStatus } from "../../../Services/backups";
import BackupEscrowBanner, { escrowMessage } from "../../../Components/Backups/BackupEscrowBanner";
import { t } from "../TimeSync/_i18nMock";

const status = (over: Partial<EscrowStatus> = {}): EscrowStatus => ({
  applies: true, encrypted_hosts: 2, covered_hosts: 1, stale_hosts: ["mail.lab"],
  signing_on: false, signing_stale: false, stale: true,
  last_export: { at: "2026-11-01T10:00:00Z", by: "bryan@example.lab", recipient: "F".repeat(40), reason: "x" },
  escrow_key: null, export_host_id: "h-1",
  ...over,
});

const show = () => render(
  <MemoryRouter initialEntries={["/backups"]}>
    <Routes>
      <Route path="/backups" element={<BackupEscrowBanner />} />
      <Route path="/hosts/:id" element={<div>host page</div>} />
    </Routes>
  </MemoryRouter>,
);

describe("BackupEscrowBanner", () => {
  beforeEach(() => vi.clearAllMocks());

  test("says which hosts the export misses and links to the export", async () => {
    vi.mocked(getEscrowStatus).mockResolvedValue(status());
    show();
    expect(await screen.findByText(/does not cover the newest keys of 1 encrypted host\(s\) \(mail\.lab\)/))
      .toBeInTheDocument();
    fireEvent.click(screen.getByText("Export the keys"));
    expect(await screen.findByText("host page")).toBeInTheDocument();
  });

  test("shows nothing when escrow is current, or does not apply (Community)", async () => {
    vi.mocked(getEscrowStatus).mockResolvedValue(status({ stale: false, stale_hosts: [] }));
    const { container, unmount } = show();
    await waitFor(() => expect(getEscrowStatus).toHaveBeenCalled());
    expect(container.textContent).toBe("");
    unmount();
    vi.mocked(getEscrowStatus).mockResolvedValue(status({ applies: false }));
    const second = show();
    await waitFor(() => expect(getEscrowStatus).toHaveBeenCalledTimes(2));
    expect(second.container.textContent).toBe("");
  });

  test("the message says why: never, hosts, or signing", () => {
    expect(escrowMessage(t, status({ last_export: null }))).toMatch(/No break-glass key export has been made/);
    expect(escrowMessage(t, status({ stale_hosts: [], signing_stale: true })))
      .toMatch(/Snapshot signing was turned on after/);
  });
});

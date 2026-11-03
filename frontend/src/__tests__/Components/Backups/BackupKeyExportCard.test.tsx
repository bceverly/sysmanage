// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The break-glass key export without the Pro+ engine (2026-11-03): shown to a
// lapsed install with encrypted backups, never beside the Pro+ panel.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
const licensed = vi.hoisted(() => ({ value: false }));
vi.mock("../../../hooks/useModuleLicensed", () => ({
  useModuleLicensed: () => licensed.value,
  default: () => licensed.value,
}));
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, getBreakGlassInfo: vi.fn(), exportBreakGlass: vi.fn() };
});

import { getBreakGlassInfo, exportBreakGlass } from "../../../Services/backups";
import BackupKeyExportCard from "../../../Components/Backups/BackupKeyExportCard";

const AVAILABLE = { available: true, encrypted_hosts: 3, escrow_key_fingerprint: null };

describe("BackupKeyExportCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    licensed.value = false;
    globalThis.URL.createObjectURL = vi.fn(() => "blob:x");
    globalThis.URL.revokeObjectURL = vi.fn();
  });

  test("a lapsed install with encrypted backups can still take its keys out", async () => {
    vi.mocked(getBreakGlassInfo).mockResolvedValue(AVAILABLE);
    vi.mocked(exportBreakGlass).mockResolvedValue({ blob: new Blob(["x"]), name: "k.tar.asc" });
    render(<BackupKeyExportCard />);
    fireEvent.click(await screen.findByText("Break-glass key export"));
    fireEvent.change(screen.getByLabelText("Your OpenPGP PUBLIC key (armored)"), {
      target: { value: "-----BEGIN PGP PUBLIC KEY BLOCK-----" },
    });
    fireEvent.change(screen.getByLabelText("Why (goes in the audit log and the README)"), {
      target: { value: "license lapsed, escrow" },
    });
    fireEvent.click(screen.getByText("Export and download"));
    await waitFor(() =>
      expect(exportBreakGlass).toHaveBeenCalledWith(
        "license lapsed, escrow", "-----BEGIN PGP PUBLIC KEY BLOCK-----",
      ),
    );
  });

  test("nothing when licensed: the Pro+ panel does this", () => {
    licensed.value = true;
    const { container } = render(<BackupKeyExportCard />);
    expect(container).toBeEmptyDOMElement();
    expect(getBreakGlassInfo).not.toHaveBeenCalled();
  });

  test("nothing with no encrypted backups", async () => {
    vi.mocked(getBreakGlassInfo).mockResolvedValue({ ...AVAILABLE, available: false, encrypted_hosts: 0 });
    const { container } = render(<BackupKeyExportCard />);
    await waitFor(() => expect(getBreakGlassInfo).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The network shares a host's backup leaves out: the dialog's note and the
// Backups row's icon (2026-11-01).

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

import { NetworkMountsIcon, NetworkMountsNote } from "../../../Components/Backups/NetworkMountsNote";

const mounts = {
  excluded: ["/home/me/dev/productions", "/home/me/dev/RAMBOUILLET-backup"],
  kept: ["/home/me/rambo_forensic_copy"],
  native: false,
};

describe("NetworkMountsNote", () => {
  test("names what was left out, what was kept, and why", () => {
    render(<NetworkMountsNote mounts={mounts} />);
    expect(screen.getByText(
      "Left out automatically (network mounts on this host): /home/me/dev/productions, /home/me/dev/RAMBOUILLET-backup",
    )).toBeInTheDocument();
    expect(screen.getByText(/"Also back up" names a path inside them: \/home\/me\/rambo_forensic_copy/))
      .toBeInTheDocument();
    expect(screen.getByText("A network share is best backed up on the server that owns it."))
      .toBeInTheDocument();
  });

  test("says nothing when nothing was left out, or nothing was reported", () => {
    const { container, rerender } = render(<NetworkMountsNote mounts={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<NetworkMountsNote mounts={{ excluded: [], kept: [], native: true }} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("the row's icon carries the same note", () => {
    render(<NetworkMountsIcon mounts={{ ...mounts, kept: [] }} />);
    expect(screen.getByLabelText(/^Left out automatically \(network mounts on this host\)/))
      .toBeInTheDocument();
    const { container } = render(<NetworkMountsIcon mounts={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("a restate that skips them itself: what its last capture left out, with types", () => {
    render(<NetworkMountsNote mounts={{
      excluded: ["/data/nfs", "/media/auto"], kept: [], native: true,
      skipped: [{ path: "/data/nfs", type: "nfs4" }, { path: "/media/auto", type: "" }],
    }} />);
    expect(screen.getByText(
      "Left out of the last backup by restate (network mounts on this host): /data/nfs (nfs4), /media/auto",
    )).toBeInTheDocument();
    expect(screen.queryByText(/^Left out automatically/)).not.toBeInTheDocument();
  });
});

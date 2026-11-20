// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Hosts whose disk is nearly full (2026-11-20): said before an update runs
// out of room part-way.

import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const fill = (text: string, opts?: Record<string, unknown>) =>
    text.replace(/\{\{(\w+)\}\}/g, (_m, key) => String(opts?.[key] ?? ""));
  const value = {
    t: (k: string, f?: string | Record<string, unknown>, o?: Record<string, unknown>) =>
      typeof f === "string" ? fill(f, o) : k,
    i18n: { language: "en" },
  };
  return { useTranslation: () => value };
});
vi.mock("../../Services/hosts", () => ({ doGetHostsSummary: vi.fn() }));

import { doGetHostsSummary } from "../../Services/hosts";
import type { SysManageHost } from "../../Services/hosts";
import DiskSpaceNotice from "../../Components/DiskSpaceNotice";

const host = (over: Partial<SysManageHost>): SysManageHost =>
  ({ id: "h1", fqdn: "fp.example", active: true, ...over }) as SysManageHost;
const FULL = host({ disk_nearly_full: true, disk_used_percent: 99.3, disk_fullest_mount: "/",
  disk_available_bytes: 1363148 });
const OLD_AGENT = host({ id: "h2", fqdn: "old.example", disk_nearly_full: true, disk_used_percent: 91.2 });
const show = (ui: ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

beforeEach(() => vi.clearAllMocks());

test("a host's own page says which disk and what is left", () => {
  show(<DiskSpaceNotice host={FULL} />);
  expect(screen.getByText("Disk nearly full")).toBeInTheDocument();
  expect(screen.getByText(/\/ is 99% full \(1\.3 MB free\)/)).toBeInTheDocument();
  expect(screen.getByTestId("disk-space-notice").className).toMatch(/Error/);
});

test("nothing while the disk has room", () => {
  const { container } = show(<DiskSpaceNotice host={host({ disk_used_percent: 33 })} />);
  expect(container).toBeEmptyDOMElement();
});

test("the dashboard names the hosts, an older agent by percentage", async () => {
  vi.mocked(doGetHostsSummary).mockResolvedValue({ disk_nearly_full: 2, disk_hosts: [FULL, OLD_AGENT] } as never);
  show(<DiskSpaceNotice />);
  expect(await screen.findByText("old.example")).toBeInTheDocument();
  expect(screen.getByText(/Its fullest disk is 91% full/)).toBeInTheDocument();
});

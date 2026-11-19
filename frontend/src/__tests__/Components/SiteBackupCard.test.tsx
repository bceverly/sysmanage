// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A federated site's backup status on the coordinator's site page (27.1):
// counts, sizes and times only -- the backups stay at the site.

import { render, screen } from "@testing-library/react";
import { vi, test, expect } from "vitest";

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

import { SiteBackupCard } from "../../Components/SiteBackupCard";
import type { FederationBackupRollup } from "../../Services/federationBackup";

const BACKUP: FederationBackupRollup = {
  configured: true,
  target_problem: true,
  hosts_with_policy: 4,
  attention_count: 2,
  never_backed_up: 1,
  repository_bytes: 2048,
  oldest_last_good_at: "2026-11-10T01:00:00",
  status_counts: { ok: 2, overdue: 1, failed: 1 },
  verification_counts: { verified: 2, failed: 1 },
  attention_hosts: [
    { host_id: "h1", fqdn: "c.lan", status: "failed", last_good_at: null },
    { host_id: "h2", fqdn: "b.lan", status: "overdue", last_good_at: "2026-11-10T01:00:00" },
  ],
};

test("nothing synced yet says so", () => {
  render(<SiteBackupCard backup={null} />);
  expect(screen.getByText("No backup status synced from this site yet.")).toBeInTheDocument();
});

test("a site without backups set up says so", () => {
  render(<SiteBackupCard backup={{ ...BACKUP, configured: false }} />);
  expect(screen.getByText("Backups are not set up on this site's server.")).toBeInTheDocument();
  expect(screen.queryByText("Hosts covered: 4")).not.toBeInTheDocument();
});

test("the status shows counts, storage and the hosts to look at", () => {
  render(<SiteBackupCard backup={BACKUP} />);
  expect(screen.getByText("Hosts covered: 4")).toBeInTheDocument();
  expect(screen.getByText("Need attention: 2")).toBeInTheDocument();
  expect(screen.getByText("Never backed up: 1")).toBeInTheDocument();
  expect(screen.getByText("The site's backup storage needs attention")).toBeInTheDocument();
  expect(screen.getByText("Verified: 2")).toBeInTheDocument();
  expect(screen.getByText("Verification failed: 1")).toBeInTheDocument();
  expect(screen.getByText(/c\.lan/)).toHaveTextContent("never backed up");
  expect(screen.getByText(/b\.lan/)).toHaveTextContent("last good");
  expect(screen.getByText(/Stored at the site:/)).toBeInTheDocument();
});

test("a healthy site shows no warnings", () => {
  render(
    <SiteBackupCard
      backup={{
        ...BACKUP, target_problem: false, attention_count: 0, never_backed_up: 0,
        attention_hosts: [], status_counts: { ok: 4 }, verification_counts: {},
      }}
    />,
  );
  expect(screen.queryByText(/Never backed up/)).not.toBeInTheDocument();
  expect(screen.queryByText("The site's backup storage needs attention")).not.toBeInTheDocument();
  expect(screen.queryByText("Hosts to look at on the site")).not.toBeInTheDocument();
});

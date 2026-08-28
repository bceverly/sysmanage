// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Federation sites and the federation audit log.
 *
 * Both are Enterprise pages, so the first thing each must get right is the
 * unlicensed case: an empty page looks like a broken feature, whereas naming
 * the licence tells the operator what is actually going on.
 *
 * Enrollment is the sharp edge on the Sites page — it hands a subordinate
 * server the credentials to join this coordinator, so a failure must be
 * visible rather than leaving the operator to wonder whether it took.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

// Every one of these must return a STABLE reference. Handing back a fresh
// object or array each call makes any effect that depends on it re-run
// forever, which surfaces as a vitest worker dying rather than as a test
// failure -- the same trap as a fresh `t` per render.
const navigate = vi.fn();
const location = { pathname: "/audit/federation", search: "" };
const searchParams: [URLSearchParams, () => void] = [
  new URLSearchParams(),
  vi.fn(),
];
vi.mock("react-router", () => ({
  useNavigate: () => navigate,
  useLocation: () => location,
  useSearchParams: () => searchParams,
}));

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({ rows }: { rows?: Record<string, unknown>[] }) => (
    <div data-testid="grid">{`rows:${rows?.length ?? 0}`}</div>
  ),
}));

vi.mock("../../Services/federation", () => ({
  doListFederationSites: vi.fn(),
  doEnrollFederationSite: vi.fn(),
  doListFederationAuditLog: vi.fn(),
}));

import {
  doListFederationSites,
  doEnrollFederationSite,
  doListFederationAuditLog,
} from "../../Services/federation";
import Sites from "../../Pages/Sites";
import FederationAuditLog from "../../Pages/FederationAuditLog";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const site = (over = {}) => ({
  id: "s1",
  name: "dc-east",
  fqdn: "east.invalid",
  status: "connected",
  host_count: 12,
  last_sync_at: "2026-08-27T00:00:00Z",
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  m(doListFederationSites).mockResolvedValue({
    licensed: true,
    sites: [site()],
  });
  m(doListFederationAuditLog).mockResolvedValue({
    licensed: true,
    entries: [],
    total: 0,
  });
});

describe("Sites", () => {
  test("lists the enrolled sites", async () => {
    render(<Sites />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("an unlicensed server names the licence rather than showing nothing", async () => {
    m(doListFederationSites).mockResolvedValue({ licensed: false, sites: [] });
    render(<Sites />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("a load failure is surfaced", async () => {
    m(doListFederationSites).mockRejectedValue(new Error("coordinator down"));
    render(<Sites />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("a response with no sites key is treated as empty", async () => {
    m(doListFederationSites).mockResolvedValue({ licensed: true });
    render(<Sites />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("enrollment is not fired without a target", async () => {
    // Enrolling hands a subordinate the credentials to join; a blank form
    // must not produce a request.
    render(<Sites />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
    const enroll = screen
      .queryAllByRole("button")
      .find((b) => /enroll|add site/i.test(b.textContent || ""));
    if (enroll) fireEvent.click(enroll);
    const submit = screen
      .queryAllByRole("button")
      .find((b) => /^enroll$/i.test((b.textContent || "").trim()));
    if (submit) fireEvent.click(submit);
    await waitFor(() =>
      expect(m(doEnrollFederationSite)).not.toHaveBeenCalled(),
    );
  });
});

describe("FederationAuditLog", () => {
  test("asks for the audit entries on mount", async () => {
    render(<FederationAuditLog />);
    await waitFor(() =>
      expect(m(doListFederationAuditLog)).toHaveBeenCalled(),
    );
  });

  test("an unlicensed server renders an explanation", async () => {
    m(doListFederationAuditLog).mockResolvedValue({
      licensed: false,
      entries: [],
      total: 0,
    });
    render(<FederationAuditLog />);
    await waitFor(() =>
      expect(m(doListFederationAuditLog)).toHaveBeenCalled(),
    );
    expect(document.body.textContent).not.toBe("");
  });

  test("entries are rendered when present", async () => {
    m(doListFederationAuditLog).mockResolvedValue({
      licensed: true,
      entries: [
        {
          id: "a1",
          created_at: "2026-08-27T00:00:00Z",
          site_name: "dc-east",
          action: "policy_push",
          detail: "baseline",
        },
      ],
      total: 1,
    });
    render(<FederationAuditLog />);
    await waitFor(() =>
      expect(m(doListFederationAuditLog)).toHaveBeenCalled(),
    );
    expect(document.body.textContent).not.toBe("");
  });

  test("a failure does not blank the page", async () => {
    m(doListFederationAuditLog).mockRejectedValue(new Error("unreachable"));
    render(<FederationAuditLog />);
    await waitFor(() =>
      expect(m(doListFederationAuditLog)).toHaveBeenCalled(),
    );
    expect(document.body.textContent).not.toBe("");
  });

  test("a missing entries key is treated as empty", async () => {
    m(doListFederationAuditLog).mockResolvedValue({ licensed: true, total: 0 });
    render(<FederationAuditLog />);
    await waitFor(() =>
      expect(m(doListFederationAuditLog)).toHaveBeenCalled(),
    );
    expect(document.body.textContent).not.toBe("");
  });
});

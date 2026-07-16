// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, test, expect } from "vitest";

// `t` and the returned object MUST be stable across renders (the real
// react-i18next memoises them) — a fresh `t` per call breaks downstream
// useCallback/useEffect deps into an infinite render loop.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = fallback || key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  const value = { t, i18n: { language: "en" } };
  return { useTranslation: () => value };
});

vi.mock("../../Services/federation", () => ({
  doListFederationSites: vi.fn(),
}));

import { doListFederationSites } from "../../Services/federation";
import SitesTiles from "../../Pages/SitesTiles";

const mockList = doListFederationSites as unknown as ReturnType<typeof vi.fn>;

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/sites/tiles"]}>
      <SitesTiles />
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

test("shows the Enterprise upsell when unlicensed", async () => {
  mockList.mockResolvedValue({ licensed: false });
  renderPage();
  expect(
    await screen.findByText(/Multi-site federation requires Enterprise/i),
  ).toBeTruthy();
});

test("renders the coordinator hub and a tile per site", async () => {
  mockList.mockResolvedValue({
    licensed: true,
    sites: [
      { id: "s1", name: "Alpha", status: "enrolled", host_count: 3 },
      { id: "s2", name: "Bravo", status: "suspended", host_count: 0 },
    ],
  });
  renderPage();
  expect(await screen.findByText("Coordinator")).toBeTruthy();
  expect(screen.getByText("Alpha")).toBeTruthy();
  expect(screen.getByText("Bravo")).toBeTruthy();
  // Aggregate hub count reflects 1 enrolled.
  expect(screen.getByText(/1 enrolled/i)).toBeTruthy();
});

test("renders the empty state with no sites", async () => {
  mockList.mockResolvedValue({ licensed: true, sites: [] });
  renderPage();
  expect(await screen.findByText(/No sites enrolled yet/i)).toBeTruthy();
});

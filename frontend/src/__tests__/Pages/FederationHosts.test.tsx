// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, test, expect } from "vitest";

// NB: `t` and the returned object MUST be stable across renders.  The real
// react-i18next memoises them; a factory that returns a fresh `t` on every
// useTranslation() call breaks downstream useCallback/useEffect deps (e.g.
// FederationHosts' fetchData) into an infinite render loop that exhausts the
// worker heap.  Define them once here.
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
  doSearchFederationHosts: vi.fn(),
  doGetFederationHostDetail: vi.fn(),
  doDispatchFederationCommand: vi.fn(),
}));

// Stub the dispatch dialog — its own behaviour is covered in its dedicated
// test; rendering its full MUI tree here just bloats the worker heap.
vi.mock("../../Components/FederationCommandDispatchDialog", () => ({
  default: () => null,
}));

import {
  doSearchFederationHosts,
  doGetFederationHostDetail,
} from "../../Services/federation";
import FederationHosts from "../../Pages/FederationHosts";

const mockSearch =
  doSearchFederationHosts as unknown as ReturnType<typeof vi.fn>;
const mockDetail =
  doGetFederationHostDetail as unknown as ReturnType<typeof vi.fn>;

function renderPage(initial = "/federation/hosts") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <FederationHosts />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockDetail.mockResolvedValue({ licensed: true, host: null });
});

test("renders the Enterprise upsell when unlicensed", async () => {
  mockSearch.mockResolvedValue({ licensed: false });
  renderPage();
  expect(
    await screen.findByText(/Multi-site federation requires Enterprise/i),
  ).toBeTruthy();
});

test("renders host rows from the directory", async () => {
  mockSearch.mockResolvedValue({
    licensed: true,
    total: 1,
    hosts: [
      {
        host_id: "h1",
        site_id: "sA",
        fqdn: "web01.example.com",
        ipv4: "10.0.0.1",
        os_family: "ubuntu",
        status: "up",
      },
    ],
  });
  renderPage();
  expect(await screen.findByText("web01.example.com")).toBeTruthy();
});

test("selecting a host reveals the bulk-dispatch toolbar", async () => {
  mockSearch.mockResolvedValue({
    licensed: true,
    total: 1,
    hosts: [
      {
        host_id: "h1",
        site_id: "sA",
        fqdn: "web01.example.com",
        status: "up",
      },
    ],
  });
  renderPage();
  await screen.findByText("web01.example.com");
  // Row checkbox (the header is the first checkbox, the row is the second).
  const checkboxes = screen.getAllByRole("checkbox");
  fireEvent.click(checkboxes[checkboxes.length - 1]);
  await waitFor(() =>
    expect(screen.getByText(/1 hosts selected/i)).toBeTruthy(),
  );
  expect(screen.getByTestId("bulk-dispatch-button")).toBeTruthy();
});

test("scoped-to-site chip shows when ?site_id= is present", async () => {
  mockSearch.mockResolvedValue({ licensed: true, total: 0, hosts: [] });
  renderPage("/federation/hosts?site_id=sA");
  expect(await screen.findByText(/Scoped to one site/i)).toBeTruthy();
  // The search was scoped to that site.
  await waitFor(() =>
    expect(mockSearch.mock.calls[0][0].site_id).toBe("sA"),
  );
});

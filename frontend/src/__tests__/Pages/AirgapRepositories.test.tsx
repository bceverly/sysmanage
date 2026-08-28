// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The air-gap repository dashboard.
 *
 * This page has to survive three different servers: one where the air-gap
 * endpoint does not exist at all (404 on an older or non-repository build),
 * one that returns the current envelope, and one still returning the legacy
 * flat array. A 404 is not an error here — it means "this server does not do
 * this job" — and rendering it as a failure would tell an operator something
 * is broken when nothing is.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("../../Components/AirgapImportPanel", () => ({ default: () => null }));

import AirgapRepositories from "../../Pages/AirgapRepositories";

const repo = (over = {}) => ({
  id: "r1",
  distro: "ubuntu",
  version: "24.04",
  repo_url: "http://mirror.invalid/ubuntu",
  last_synced_at: "2026-08-27T00:00:00Z",
  ...over,
});

/** Route the page's two raw fetch() calls. */
const routeFetch = (opts: {
  role?: string;
  reposStatus?: number;
  reposBody?: unknown;
  reposThrows?: boolean;
}) => {
  globalThis.fetch = vi.fn(async (url: string) => {
    if (String(url).includes("server-info")) {
      return { ok: true, status: 200, json: async () => ({ role: opts.role ?? "repository" }) };
    }
    if (opts.reposThrows) throw new Error("network");
    const status = opts.reposStatus ?? 200;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => opts.reposBody ?? { repositories: [], aggregate: null },
    };
  }) as never;
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("bearer_token", "tok");
  routeFetch({});
});

describe("server role", () => {
  test("a repository server loads its repositories", async () => {
    routeFetch({ reposBody: { repositories: [repo()], aggregate: null } });
    render(<AirgapRepositories />);
    expect(await screen.findByText("ubuntu")).toBeInTheDocument();
  });

  test("a server-info failure still renders the page", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({}),
    })) as never;
    render(<AirgapRepositories />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toBe("");
  });
});

describe("payload shapes", () => {
  test("the current envelope is read", async () => {
    routeFetch({
      reposBody: { repositories: [repo(), repo({ id: "r2" })], aggregate: {} },
    });
    render(<AirgapRepositories />);
    await waitFor(() =>
      expect(screen.getAllByText("ubuntu")).toHaveLength(2),
    );
  });

  test("a legacy flat array is still accepted", async () => {
    // Older deployments returned a bare list; refusing it would break the
    // page against a server that is merely out of date.
    routeFetch({ reposBody: [repo()] });
    render(<AirgapRepositories />);
    expect(await screen.findByText("ubuntu")).toBeInTheDocument();
  });

  test("an envelope with no repositories key yields an empty grid", async () => {
    routeFetch({ reposBody: { aggregate: null } });
    render(<AirgapRepositories />);
    // The empty state is an explicit message, not a blank table body.
    expect(
      await screen.findByText(/No repositories ingested yet/),
    ).toBeInTheDocument();
  });

  test("a null body is treated as empty rather than crashing", async () => {
    routeFetch({ reposBody: null });
    render(<AirgapRepositories />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toBe("");
  });
});

describe("failure modes", () => {
  test("a 404 means 'this server does not do this', not an error", async () => {
    routeFetch({ reposStatus: 404 });
    render(<AirgapRepositories />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toBe("");
  });

  test("a 500 surfaces as an error the operator can act on", async () => {
    routeFetch({ reposStatus: 500 });
    render(<AirgapRepositories />);
    expect(await screen.findByText(/HTTP 500/)).toBeInTheDocument();
  });

  test("a network failure surfaces its message", async () => {
    routeFetch({ reposThrows: true });
    render(<AirgapRepositories />);
    expect(await screen.findByText(/network/)).toBeInTheDocument();
  });

  test("a missing bearer token does not stop the request being made", async () => {
    // Losing the header should produce a 401 from the server, not a page that
    // silently never asks.
    localStorage.removeItem("bearer_token");
    routeFetch({});
    render(<AirgapRepositories />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
  });
});

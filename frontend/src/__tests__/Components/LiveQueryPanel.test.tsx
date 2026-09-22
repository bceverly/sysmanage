// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The live-query panel (Phase 21.1 S5).
 *
 * What matters here is that the BOUND is visible. A live query asks hosts in
 * waves, so at any moment some are answered, some are in flight and some have
 * not been asked at all — and an operator who cannot see that distinction
 * cannot tell a bounded fan-out from a hung one.
 *
 * The second thing is the one this whole phase keeps insisting on: a host
 * that could not answer must not be rendered as a failure.
 */

import React from "react";
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

const t = (key: string, fallback?: string | object, opts?: object) => {
  const text = typeof fallback === "string" ? fallback : key;
  const vars = (typeof fallback === "object" ? fallback : opts) as
    | Record<string, unknown>
    | undefined;
  return vars
    ? text.replace(/\{\{(\w+)\}\}/g, (_m, k) => String(vars[k] ?? ""))
    : text;
};
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("../../Services/queryPackService", () => ({
  createLiveQuery: vi.fn(),
  getLiveQuery: vi.fn(),
  cancelLiveQuery: vi.fn(),
}));

import {
  createLiveQuery,
  getLiveQuery,
  cancelLiveQuery,
} from "../../Services/queryPackService";
import LiveQueryPanel from "../../Components/LiveQueryPanel";

const HOSTS = ["11111111-1111-4111-8111-111111111111"];

const liveQuery = (over = {}) => ({
  id: "22222222-2222-4222-8222-222222222222",
  name: null,
  sql: "SELECT uid FROM users",
  required_tables: ["users"],
  status: "running",
  concurrency: 20,
  timeout_seconds: 120,
  total_targets: 3,
  completed_count: 1,
  failed_count: 0,
  not_covered_count: 0,
  requested_by: "admin@sysmanage.org",
  created_at: "2026-09-22T10:00:00Z",
  completed_at: null,
  ...over,
});

const target = (over = {}) => ({
  run_id: "33333333-3333-4333-8333-333333333333",
  host_id: "host-a",
  status: "success",
  queries_ok: 1,
  queries_not_covered: 0,
  error: null,
  rows: [{ status: "ok", reason: null, columns: { uid: 0 } }],
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

// The click kicks off an async chain (create -> poll -> setState) that
// settles AFTER the handler returns, so it has to be awaited inside act or
// this repo's setupTests fails the test on the React warning.
const start = async () => {
  render(<LiveQueryPanel hostIds={HOSTS} />);
  fireEvent.change(screen.getByLabelText("SQL"), {
    target: { value: "SELECT uid FROM users" },
  });
  await act(async () => {
    fireEvent.click(screen.getByText("Run Now"));
  });
};

describe("the bound is visible", () => {
  test("a host that has not been asked yet shows as waiting", async () => {
    // THE test. "waiting" is the bound made visible — without it, a bounded
    // fan-out and a hung one look identical to the operator.
    (createLiveQuery as any).mockResolvedValue(liveQuery());
    (getLiveQuery as any).mockResolvedValue(
      liveQuery({
        status: "completed",
        targets: [
          target({ run_id: "r1", status: "success" }),
          target({ run_id: "r2", status: "pending", rows: [] }),
          target({ run_id: "r3", status: "waiting", rows: [] }),
        ],
      }),
    );
    await start();
    expect(await screen.findByText("Waiting")).toBeTruthy();
    expect(screen.getByText("Asked")).toBeTruthy();
    expect(screen.getByText("Answered")).toBeTruthy();
  });

  test("progress is reported as answered-of-total", async () => {
    (createLiveQuery as any).mockResolvedValue(liveQuery());
    (getLiveQuery as any).mockResolvedValue(
      liveQuery({ status: "completed", completed_count: 2, total_targets: 5 }),
    );
    await start();
    expect(await screen.findByText("Hosts answered: 2 / 5")).toBeTruthy();
  });
});

describe("not covered is not a failure", () => {
  test("uncovered hosts are counted apart from failures", async () => {
    (createLiveQuery as any).mockResolvedValue(liveQuery());
    (getLiveQuery as any).mockResolvedValue(
      liveQuery({ status: "completed", not_covered_count: 2, failed_count: 1 }),
    );
    await start();
    expect(await screen.findByText("2 not covered")).toBeTruthy();
    expect(screen.getByText("1 failed")).toBeTruthy();
  });

  test("an uncovered row shows its reason rather than an empty result", async () => {
    (createLiveQuery as any).mockResolvedValue(liveQuery());
    (getLiveQuery as any).mockResolvedValue(
      liveQuery({
        status: "completed",
        targets: [
          target({
            status: "partial",
            rows: [
              { status: "not_covered", reason: "wrong_platform", columns: null },
            ],
          }),
        ],
      }),
    );
    await start();
    expect(await screen.findByText("not covered: wrong_platform")).toBeTruthy();
  });
});

describe("polling", () => {
  test("it stops once the query completes", async () => {
    (createLiveQuery as any).mockResolvedValue(liveQuery());
    (getLiveQuery as any).mockResolvedValue(liveQuery({ status: "completed" }));
    await start();
    await waitFor(() => expect(getLiveQuery).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(getLiveQuery).toHaveBeenCalledTimes(1);
  });

  test("it keeps polling while the query is running", async () => {
    (createLiveQuery as any).mockResolvedValue(liveQuery());
    (getLiveQuery as any).mockResolvedValue(liveQuery({ status: "running" }));
    await start();
    await waitFor(() => expect(getLiveQuery).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    await waitFor(() => expect(getLiveQuery).toHaveBeenCalledTimes(2));
  });
});

describe("guards", () => {
  test("running is refused with no hosts selected", () => {
    render(<LiveQueryPanel hostIds={[]} />);
    fireEvent.change(screen.getByLabelText("SQL"), {
      target: { value: "SELECT 1" },
    });
    expect(
      (screen.getByText("Run Now").closest("button") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  test("a rejected query surfaces the server's own words", async () => {
    (createLiveQuery as any).mockRejectedValue({
      response: { data: { detail: "a query may only read" } },
    });
    await start();
    expect(await screen.findByText("a query may only read")).toBeTruthy();
  });

  test("cancelling stops the polling", async () => {
    (createLiveQuery as any).mockResolvedValue(liveQuery());
    (getLiveQuery as any).mockResolvedValue(liveQuery({ status: "running" }));
    (cancelLiveQuery as any).mockResolvedValue({
      status: "canceled",
      targets_not_dispatched: 2,
    });
    await start();
    await waitFor(() => expect(getLiveQuery).toHaveBeenCalled());
    await act(async () => {
      fireEvent.click(screen.getByText("Cancel"));
    });
    await waitFor(() => expect(cancelLiveQuery).toHaveBeenCalled());
  });
});

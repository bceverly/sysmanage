// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Fleet job progress.
 *
 * What this panel has to get right is honesty about scale. A bar at 99.9%
 * looks identical to one at 100%, so the COUNTS carry the message: "3,997 of
 * 4,000 — 3 failed" is the sentence an operator acts on. And a job whose
 * status went red because three machines of four thousand were mid-reboot
 * would be ignored within a week, so `completed` with a failure count is the
 * right answer and is rendered as such.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
  let s = typeof fallback === "string" ? fallback : key;
  if (opts) {
    for (const [k, v] of Object.entries(opts)) {
      s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
    }
  }
  return s;
};
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("../../Services/configFleetService", () => ({
  getJobs: vi.fn(),
  getJobTargets: vi.fn(),
  cancelJob: vi.fn(),
}));

import {
  getJobs,
  getJobTargets,
  cancelJob,
} from "../../Services/configFleetService";
import ConfigJobsPanel from "../../Components/ConfigJobsPanel";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const job = (over = {}) => ({
  id: "j1",
  template_id: "t1",
  template_name: "nightly baseline",
  profile_id: "p1",
  profile_name: "baseline",
  inventory_name: "web tier",
  status: "completed",
  check_mode: false,
  concurrency: 20,
  total_targets: 4000,
  succeeded_count: 3997,
  failed_count: 3,
  skipped_count: 0,
  outstanding_count: 0,
  requested_by: "op",
  detail: null,
  created_at: null,
  started_at: null,
  finished_at: null,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  m(getJobs).mockResolvedValue([job()]);
  m(getJobTargets).mockResolvedValue([]);
});

describe("ConfigJobsPanel", () => {
  test("an empty list says how to start one rather than showing nothing", async () => {
    m(getJobs).mockResolvedValue([]);
    render(<ConfigJobsPanel canCancel />);
    expect(
      await screen.findByText(/Launch one from the Templates tab/i),
    ).toBeInTheDocument();
  });

  test("progress is reported as counts, not only as a bar", async () => {
    // A bar at 99.9% is indistinguishable from one at 100%; the numbers are
    // what an operator reads.
    render(<ConfigJobsPanel canCancel />);
    expect(
      await screen.findByText(/3997 succeeded, 3 failed/i),
    ).toBeInTheDocument();
  });

  test("a job with some failures still reports completed", async () => {
    // Deliberate: the status answers "did this job do its work", not "is
    // every host happy". A status that goes red on every fleet run is ignored.
    render(<ConfigJobsPanel canCancel />);
    expect(await screen.findByText("completed")).toBeInTheDocument();
  });

  test("a dry run is labelled so nobody thinks the fleet was changed", async () => {
    m(getJobs).mockResolvedValue([job({ check_mode: true })]);
    render(<ConfigJobsPanel canCancel />);
    expect(await screen.findByText("Dry run")).toBeInTheDocument();
  });

  test("cancel is offered only while a job is still moving", async () => {
    render(<ConfigJobsPanel canCancel />);
    await screen.findByText("completed");
    expect(screen.queryByText("Cancel")).not.toBeInTheDocument();
  });

  test("a running job can be cancelled", async () => {
    m(getJobs).mockResolvedValue([job({ status: "running" })]);
    m(cancelJob).mockResolvedValue(job({ status: "canceled" }));
    render(<ConfigJobsPanel canCancel />);
    fireEvent.click(await screen.findByText("Cancel"));
    await waitFor(() => expect(cancelJob).toHaveBeenCalledWith("j1", expect.any(String)));
  });

  test("without the run permission there is no cancel button", async () => {
    m(getJobs).mockResolvedValue([job({ status: "running" })]);
    render(<ConfigJobsPanel canCancel={false} />);
    await screen.findByText("running");
    expect(screen.queryByText("Cancel")).not.toBeInTheDocument();
  });

  test("the host list names which machines failed and why", async () => {
    // The whole reason a job keeps a row per host: "which twelve of the four
    // thousand" must be answerable without a log search.
    m(getJobTargets).mockResolvedValue([
      {
        id: "tg1",
        job_id: "j1",
        host_id: "h1",
        host_fqdn: "web01.invalid",
        status: "failed",
        command_id: "c1",
        run_id: "r1",
        detail: "executor_missing",
        queued_at: null,
        finished_at: null,
      },
    ]);
    render(<ConfigJobsPanel canCancel />);
    fireEvent.click(await screen.findByText("Per-host results"));
    expect(await screen.findByText("web01.invalid")).toBeInTheDocument();
    expect(screen.getByText("executor_missing")).toBeInTheDocument();
  });

  test("a job that could not proceed explains itself", async () => {
    m(getJobs).mockResolvedValue([
      job({ status: "failed", detail: "the profile this job runs was deleted" }),
    ]);
    render(<ConfigJobsPanel canCancel />);
    expect(
      await screen.findByText(/the profile this job runs was deleted/i),
    ).toBeInTheDocument();
  });

  test("a failure to load says so instead of rendering an empty page", async () => {
    m(getJobs).mockRejectedValue({
      response: { data: { detail: "the engine is not available" } },
    });
    render(<ConfigJobsPanel canCancel />);
    expect(
      await screen.findByText("the engine is not available"),
    ).toBeInTheDocument();
  });
});

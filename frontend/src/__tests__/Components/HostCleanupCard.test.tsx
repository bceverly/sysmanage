// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Old kernels and unneeded packages on a host (27.8): what is kept and why,
// no cleanup while the running kernel is unproven, and removing the plan.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
vi.mock("../../Services/packageCleanup", () => ({
  packageCleanupService: { state: vi.fn(), plan: vi.fn(), apply: vi.fn() },
}));

import { packageCleanupService } from "../../Services/packageCleanup";
import type { CleanupRun, CleanupState } from "../../Services/packageCleanup";
import HostCleanupCard from "../../Components/HostDetail/HostCleanupCard";

const svc = packageCleanupService as unknown as Record<string, ReturnType<typeof vi.fn>>;

const run = (over: Partial<CleanupRun>): CleanupRun => ({
  id: "r1", mode: "plan", status: "planned", trigger: "manual", requested_by: "a",
  protected: [], approved: null, kept: [], running_kernel: "6.8.0-139-generic", error: null,
  created_at: "2026-11-27T12:00:00", completed_at: "2026-11-27T12:01:00",
  packages: [{ name: "linux-image-6.8.0-94-generic", kernel: "6.8.0-94", reason: "old_kernel" },
             { name: "libfoo1", kernel: null, reason: "unneeded" }],
  ...over,
});

const state = (over: Partial<CleanupState>): CleanupState => ({
  running_kernel: "6.8.0-139-generic",
  installed_kernels: ["6.8.0-151-generic", "6.8.0-139-generic", "6.8.0-94-generic"],
  proven_kernels: ["6.8.0-139-generic"],
  protected: [{ release: "6.8.0-139-generic", reason: "running" },
              { release: "6.8.0-151-generic", reason: "newest" }],
  refusal: null, runs: [], ...over,
});

beforeEach(() => {
  Object.values(svc).forEach((f) => f.mockReset());
});

test("shows the kernels kept and why", async () => {
  svc.state.mockResolvedValue(state({}));
  render(<HostCleanupCard hostId="h1" />);
  expect(await screen.findByText(/3 kernels installed, 1 of them old/)).toBeTruthy();
  expect(screen.getByText(/Kept: 6.8.0-139-generic \(running now\)/)).toBeTruthy();
  expect(screen.getByText(/Kept: 6.8.0-151-generic \(newest installed/)).toBeTruthy();
});

test("an unproven running kernel blocks the cleanup and says why", async () => {
  svc.state.mockResolvedValue(state({ refusal: "running_kernel_not_proven", protected: [] }));
  render(<HostCleanupCard hostId="h1" />);
  expect(await screen.findByText(/stayed up for 15 minutes/)).toBeTruthy();
  expect((screen.getByRole("button", { name: "Plan cleanup" }) as HTMLButtonElement).disabled).toBe(true);
});

test("removes exactly the planned packages", async () => {
  svc.state.mockResolvedValue(state({ runs: [run({})] }));
  svc.apply.mockResolvedValue(run({ mode: "apply", status: "queued" }));
  render(<HostCleanupCard hostId="h1" />);
  expect(await screen.findByText(/old kernel 6.8.0-94/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Remove the packages listed (2)" }));
  await waitFor(() => expect(svc.apply).toHaveBeenCalledWith("h1", ["linux-image-6.8.0-94-generic", "libfoo1"]));
});

test("asks for a plan", async () => {
  svc.state.mockResolvedValue(state({}));
  svc.plan.mockResolvedValue(run({ status: "queued" }));
  render(<HostCleanupCard hostId="h1" />);
  fireEvent.click(await screen.findByRole("button", { name: "Plan cleanup" }));
  await waitFor(() => expect(svc.plan).toHaveBeenCalledWith("h1"));
});

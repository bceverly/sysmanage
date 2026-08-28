// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Host Detail RBAC resolution.
 *
 * Two properties matter, and they pull in opposite directions.
 *
 * **Fail closed.** Every flag starts false and stays false until a permission
 * is affirmatively granted. A flag that defaulted true would show an operator
 * a button they cannot use, and the failure would land on the far side of a
 * dispatched command.
 *
 * **Say so when it fails.** Failing closed silently is how you get a page of
 * dead buttons with no explanation. An expired session must leave a trace,
 * not just an empty permission set. Scripts.tsx carries the same rule after
 * hitting exactly this.
 */

import { renderHook, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach, afterEach } from "vitest";

vi.mock("../../../Services/permissions", async (orig) => {
  const actual =
    await orig<typeof import("../../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import {
  hasPermission,
  SecurityRoles,
} from "../../../Services/permissions";
import { useHostPermissions } from "../../../Components/HostDetail/useHostPermissions";

const mocked = () => hasPermission as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("resolution", () => {
  test("every flag is false before anything resolves", () => {
    mocked().mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useHostPermissions());
    expect(Object.values(result.current).every((v) => v === false)).toBe(true);
  });

  test("a fully privileged user gets every flag", async () => {
    mocked().mockResolvedValue(true);
    const { result } = renderHook(() => useHostPermissions());
    await waitFor(() =>
      expect(Object.values(result.current).every((v) => v === true)).toBe(true),
    );
  });

  test("flags track their own role, not each other", async () => {
    // One granted role must not light up the rest of the page.
    mocked().mockImplementation(async (role: unknown) =>
      role === SecurityRoles.ENABLE_KVM ? true : false,
    );
    const { result } = renderHook(() => useHostPermissions());
    await waitFor(() => expect(result.current.canEnableKvm).toBe(true));
    expect(result.current.canEnableWsl).toBe(false);
    expect(result.current.canEditTags).toBe(false);
    expect(result.current.canRemoveAntivirus).toBe(false);
  });

  test("permissions are resolved once, not per render", async () => {
    mocked().mockResolvedValue(true);
    const { result, rerender } = renderHook(() => useHostPermissions());
    await waitFor(() => expect(result.current.canEditTags).toBe(true));
    const callsAfterMount = mocked().mock.calls.length;
    rerender();
    rerender();
    expect(mocked().mock.calls.length).toBe(callsAfterMount);
  });
});

/* eslint-disable no-unused-vars */
// Parameter names in a TYPE are flagged by the base no-unused-vars rule, which
// is the one active in test files (the TS-aware rule is off there).
declare const process: {
  on: (event: string, handler: () => void) => void;
  off: (event: string, handler: () => void) => void;
};
/* eslint-enable no-unused-vars */

describe("failure", () => {
  // No `vi.spyOn(console, 'error')` here on purpose: setupTests.ts wraps the
  // console to catch act() warnings, and a per-file spy replaces that wrapper
  // and opts the file out of those checks -- which it says is exactly where
  // act() warnings have hidden before. So the catch is proved by the absence
  // of an unhandled rejection instead.
  test("an expired session leaves every flag false", async () => {
    (hasPermission as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("401"),
    );
    const { result } = renderHook(() => useHostPermissions());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(Object.values(result.current).every((v) => v === false)).toBe(true);
  });

  test("the rejection is caught, not left unhandled", async () => {
    // This is the assertion that distinguishes "handled and reported" from
    // "silently exploded": without the try/catch the Promise.all rejection
    // escapes the effect entirely.
    const unhandled = vi.fn();
    process.on("unhandledRejection", unhandled);
    (hasPermission as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("network"),
    );

    renderHook(() => useHostPermissions());
    await new Promise((resolve) => setTimeout(resolve, 50));

    process.off("unhandledRejection", unhandled);
    expect(unhandled).not.toHaveBeenCalled();
  });
});

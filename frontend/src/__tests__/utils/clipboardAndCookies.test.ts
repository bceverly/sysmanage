// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Clipboard and cookie helpers.
 *
 * The clipboard helper exists because `navigator.clipboard` is undefined
 * outside a secure context — a freshly-installed server reached over plain
 * HTTP by IP. That is not an edge case, it is the first hour of every
 * install, and it is why the Copy buttons once did nothing. So the fallback
 * path is tested as a first-class outcome, not as an afterthought.
 */

import { vi, describe, test, expect, beforeEach, afterEach } from "vitest";

import { copyToClipboard } from "../../utils/clipboard";
import {
  setSecureCookie,
  getCookie,
  deleteCookie,
  areCookiesEnabled,
  REMEMBER_ME_COOKIE_NAME,
} from "../../utils/cookieUtils";


// jsdom does not implement document.execCommand at all, so there is no
// property to spy on -- it has to be defined before it can be stubbed.
type ExecDoc = { execCommand?: (_c: string) => boolean };
const stubExec = (impl: () => boolean) => {
  (globalThis.document as unknown as ExecDoc).execCommand = vi.fn(impl);
  return (globalThis.document as unknown as ExecDoc).execCommand as ReturnType<
    typeof vi.fn
  >;
};
const clearExec = () => {
  delete (globalThis.document as unknown as ExecDoc).execCommand;
};

describe("copyToClipboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    clearExec();
  });

  test("uses the async Clipboard API when it exists", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    expect(await copyToClipboard("hello")).toBe(true);
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  test("falls back to execCommand outside a secure context", async () => {
    // navigator.clipboard is undefined over plain HTTP -- the install-day
    // case that made the Copy buttons look broken.
    vi.stubGlobal("navigator", {});
    const exec = stubExec(() => true);
    expect(await copyToClipboard("hello")).toBe(true);
    expect(exec).toHaveBeenCalledWith("copy");
  });

  test("a rejected clipboard write still falls back rather than failing", async () => {
    // Secure context, but the write was refused (focus, permissions). The
    // legacy path often still works, so giving up here would be premature.
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const exec = stubExec(() => true);
    expect(await copyToClipboard("hello")).toBe(true);
    expect(exec).toHaveBeenCalled();
  });

  test("reports false when every strategy fails so callers can say so", async () => {
    vi.stubGlobal("navigator", {});
    stubExec(() => false);
    expect(await copyToClipboard("hello")).toBe(false);
  });

  test("an execCommand that throws is caught, not propagated", async () => {
    vi.stubGlobal("navigator", {});
    stubExec(() => {
      throw new Error("nope");
    });
    expect(await copyToClipboard("hello")).toBe(false);
  });

  test("the scratch textarea never survives the copy", async () => {
    // A leaked off-screen textarea per click would accumulate silently.
    vi.stubGlobal("navigator", {});
    stubExec(() => true);
    const before = document.querySelectorAll("textarea").length;
    await copyToClipboard("hello");
    expect(document.querySelectorAll("textarea").length).toBe(before);
  });
});

describe("cookies", () => {
  beforeEach(() => {
    for (const c of document.cookie.split(";")) {
      const name = c.trim().split("=")[0];
      if (name) document.cookie = `${name}=; expires=${new Date(0).toUTCString()}; path=/`;
    }
  });

  test("a value round-trips", () => {
    setSecureCookie("alpha", "one");
    expect(getCookie("alpha")).toBe("one");
  });

  test("values with separators survive encoding", () => {
    // An unencoded ';' or '=' would truncate the cookie or split it wrongly.
    setSecureCookie("weird", "a=b; c");
    expect(getCookie("weird")).toBe("a=b; c");
  });

  test("an unknown name reads as null, not empty string", () => {
    // Callers distinguish "no cookie" from "cookie set to blank".
    expect(getCookie("never-set")).toBeNull();
  });

  test("an empty value reads back as empty, not null", () => {
    setSecureCookie("blank", "");
    expect(getCookie("blank")).toBe("");
  });

  test("deleting actually removes it", () => {
    // Deletion rides on `expires: new Date(0)`. The `maxAge: 0` alongside it
    // is dropped by a falsy check in setSecureCookie, so expires is doing all
    // the work -- if it were ever removed, deletion would silently stop.
    setSecureCookie("temp", "x");
    expect(getCookie("temp")).toBe("x");
    deleteCookie("temp");
    expect(getCookie("temp")).toBeNull();
  });

  test("cookie support is detected by a real round-trip", () => {
    expect(areCookiesEnabled()).toBe(true);
  });

  test("the probe cookie is cleaned up after detection", () => {
    areCookiesEnabled();
    expect(getCookie("__cookie_test__")).toBeNull();
  });

  test("the remembered-email cookie name is stable", () => {
    // It is read by name on the login page; renaming it silently logs
    // everyone's saved address out of existence.
    expect(REMEMBER_ME_COOKIE_NAME).toBe("sysmanage_remember_email");
  });
});

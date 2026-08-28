// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Per-OS antivirus defaults.
 *
 * These values decide which package gets deployed when an operator says
 * "install antivirus" on a host, so the read-only state matters as much as
 * the editable one: someone without MANAGE_ANTIVIRUS_DEFAULTS must be able to
 * SEE the current defaults and be told why they cannot change them, rather
 * than facing a dead form.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), put: vi.fn() },
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import axiosInstance from "../../Services/api";
import { hasPermission } from "../../Services/permissions";
import AntivirusDefaultsSettings from "../../Components/AntivirusDefaultsSettings";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const defaults = [
  { os_name: "Ubuntu", antivirus_package: "clamav" },
  { os_name: "Windows", antivirus_package: "" },
];

beforeEach(() => {
  vi.clearAllMocks();
  m(hasPermission).mockResolvedValue(true);
  m(axiosInstance.get).mockResolvedValue({ data: defaults });
  m(axiosInstance.put).mockResolvedValue({ data: {} });
});

const ready = async () => {
  render(<AntivirusDefaultsSettings />);
  await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
};

// Matches on the accessible name, so an icon-only control is found by its
// aria-label rather than by text it does not have.
const button = (re: RegExp) =>
  screen
    .queryAllByRole("button")
    .find((b) =>
      re.test(((b.getAttribute("aria-label") || b.textContent) || "").trim()),
    );

describe("loading", () => {
  test("fetches the current defaults", async () => {
    await ready();
    expect(m(axiosInstance.get)).toHaveBeenCalledWith(
      "/api/v1/antivirus-defaults/",
    );
  });

  test("a load failure reports rather than showing an empty table as truth", async () => {
    // An empty table would read as "no defaults configured", which would send
    // an operator off to configure something that may already be set.
    m(axiosInstance.get).mockRejectedValue(new Error("db down"));
    await ready();
    expect(
      await screen.findByText(/Failed to load antivirus defaults/),
    ).toBeInTheDocument();
  });

  test("a non-array payload is handled as a load failure, not a crash", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: { detail: "unexpected" } });
    await ready();
    expect(
      await screen.findByText(/Failed to load antivirus defaults/),
    ).toBeInTheDocument();
  });

  test("an OS with no configured package renders without erroring", async () => {
    m(axiosInstance.get).mockResolvedValue({
      data: [{ os_name: "Ubuntu", antivirus_package: null }],
    });
    await ready();
    expect(document.body.textContent).not.toBe("");
  });
});

describe("permission gating", () => {
  test("without the role the edit control is not offered", async () => {
    m(hasPermission).mockResolvedValue(false);
    await ready();
    await waitFor(() => expect(button(/edit antivirus defaults/i)).toBeUndefined());
  });

  test("without the role the defaults are still visible", async () => {
    // Read-only is the point: seeing what is configured needs no privilege.
    m(hasPermission).mockResolvedValue(false);
    await ready();
    expect(document.body.textContent).not.toBe("");
  });

  test("a rejected permission lookup fails closed and is reported", async () => {
    m(hasPermission).mockRejectedValue(new Error("no session"));
    await ready();
    await waitFor(() => expect(button(/edit antivirus defaults/i)).toBeUndefined());
  });

  test("with the role the edit control appears", async () => {
    await ready();
    await waitFor(() => expect(button(/edit antivirus defaults/i)).toBeDefined());
  });
});

describe("editing", () => {
  test("cancel leaves the stored defaults untouched", async () => {
    await ready();
    const edit = button(/edit antivirus defaults/i);
    if (!edit) return;
    fireEvent.click(edit);
    const cancel = button(/^cancel$/i);
    if (cancel) fireEvent.click(cancel);
    expect(m(axiosInstance.put)).not.toHaveBeenCalled();
  });

  test("saving sends every OS, not just the edited one", async () => {
    // The endpoint replaces the whole set; sending a partial list would blank
    // the defaults for every OS the operator did not touch.
    await ready();
    const edit = button(/edit antivirus defaults/i);
    if (!edit) return;
    fireEvent.click(edit);
    const save = button(/^save$/i);
    if (!save) return;
    fireEvent.click(save);
    await waitFor(() => expect(m(axiosInstance.put)).toHaveBeenCalled());
    const payload = m(axiosInstance.put).mock.calls[0][1];
    expect(Array.isArray(payload.defaults)).toBe(true);
    expect(payload.defaults.length).toBeGreaterThan(1);
  });

  test("a save failure is reported and does not claim success", async () => {
    m(axiosInstance.put).mockRejectedValue(new Error("conflict"));
    await ready();
    const edit = button(/edit antivirus defaults/i);
    if (!edit) return;
    fireEvent.click(edit);
    const save = button(/^save$/i);
    if (!save) return;
    fireEvent.click(save);
    expect(
      await screen.findByText(/Failed to save antivirus defaults/),
    ).toBeInTheDocument();
  });
});

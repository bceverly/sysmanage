// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { vi, beforeEach, afterEach, describe, test, expect } from "vitest";

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
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/machines", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../Services/machines")>();
  return {
    ...actual,
    getAssetTagScheme: vi.fn(),
    previewAssetTagScheme: vi.fn(),
    saveAssetTagScheme: vi.fn(),
  };
});

vi.mock("../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { MANAGE_ASSET_TAGS: "Manage Asset Tags" },
}));

import {
  AssetTagScheme,
  SchemeReport,
  getAssetTagScheme,
  previewAssetTagScheme,
  saveAssetTagScheme,
} from "../../Services/machines";
import { hasPermission } from "../../Services/permissions";
import AssetTagSchemeSettings from "../../Components/AssetTagSchemeSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const SCHEME: AssetTagScheme = {
  mode: "builder",
  prefix: "IT",
  separator: "-",
  digits: 5,
  suffix: "",
  pattern: "",
  enforce: false,
};

const report = (over: Partial<SchemeReport> = {}): SchemeReport => ({
  scheme: SCHEME,
  preview: "IT-00042",
  examples: { pass: ["IT-00001", "IT-12345"], fail: ["it-1", "IT00001"] },
  next_free: "IT-00007",
  tagged: 10,
  nonconforming: ["OLD-1", "legacy"],
  ...over,
});

const prefixInput = () => screen.getByTestId("asset-tag-prefix") as HTMLInputElement;

const renderLoaded = async () => {
  render(<AssetTagSchemeSettings />);
  await screen.findByTestId("asset-tag-preview");
};

beforeEach(() => {
  vi.clearAllMocks();
  m(getAssetTagScheme).mockResolvedValue(report());
  m(hasPermission).mockResolvedValue(true);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("AssetTagSchemeSettings", () => {
  test("loads the saved scheme, its preview and the nonconforming tags", async () => {
    await renderLoaded();
    expect(prefixInput().value).toBe("IT");
    expect(screen.getByTestId("asset-tag-sample")).toHaveTextContent("IT-00042");
    expect(screen.getByTestId("asset-tag-next-free")).toHaveTextContent("IT-00007");
    expect(screen.getByTestId("asset-tag-pass")).toHaveTextContent("IT-12345");
    expect(screen.getByTestId("asset-tag-fail")).toHaveTextContent("it-1");
    expect(
      screen.getByText("2 of 10 existing tags do not conform to the saved scheme."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("asset-tag-nonconforming")).toHaveTextContent("OLD-1");
    expect(screen.getByText(/never rewrites existing tags/)).toBeInTheDocument();
    expect(previewAssetTagScheme).not.toHaveBeenCalled();
  });

  test("reports when every existing tag conforms", async () => {
    m(getAssetTagScheme).mockResolvedValue(report({ nonconforming: [] }));
    await renderLoaded();
    expect(
      screen.getByText("Every existing tag conforms to the saved scheme."),
    ).toBeInTheDocument();
  });

  test("says so when no machine has a tag yet", async () => {
    m(getAssetTagScheme).mockResolvedValue(report({ nonconforming: [], tagged: 0 }));
    await renderLoaded();
    expect(screen.getByText("No machine has an asset tag yet.")).toBeInTheDocument();
  });

  test("shows an error when the scheme cannot be loaded", async () => {
    m(getAssetTagScheme).mockRejectedValue(new Error("down"));
    render(<AssetTagSchemeSettings />);
    expect(
      await screen.findByText("Could not load the asset tag scheme."),
    ).toBeInTheDocument();
  });

  test("previews the draft once, debounced, after edits stop", async () => {
    m(previewAssetTagScheme).mockResolvedValue(
      report({ scheme: { ...SCHEME, prefix: "HQ" }, preview: "HQ-00042", next_free: "HQ-00001" }),
    );
    await renderLoaded();
    vi.useFakeTimers({ shouldAdvanceTime: true });

    fireEvent.change(prefixInput(), { target: { value: "H" } });
    fireEvent.change(prefixInput(), { target: { value: "HQ" } });
    await act(async () => {
      vi.advanceTimersByTime(299);
    });
    expect(previewAssetTagScheme).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(previewAssetTagScheme).toHaveBeenCalledTimes(1);
    expect(previewAssetTagScheme).toHaveBeenCalledWith({ ...SCHEME, prefix: "HQ" });
    await waitFor(() =>
      expect(screen.getByTestId("asset-tag-sample")).toHaveTextContent("HQ-00042"),
    );
    expect(screen.getByTestId("asset-tag-next-free")).toHaveTextContent("HQ-00001");
    expect(saveAssetTagScheme).not.toHaveBeenCalled();
  });

  test("marks fields a draft preview refuses", async () => {
    m(previewAssetTagScheme).mockRejectedValue({
      response: { status: 422, data: { detail: { code: "invalid_scheme", fields: ["prefix"] } } },
    });
    await renderLoaded();
    fireEvent.change(prefixInput(), { target: { value: "bad prefix" } });
    expect(await screen.findByText(/cannot be previewed/)).toBeInTheDocument();
    expect(prefixInput()).toHaveAttribute("aria-invalid", "true");
  });

  test("regex mode swaps the builder for a pattern field with no sample number", async () => {
    const regexScheme = { ...SCHEME, mode: "regex" as const, pattern: "^[A-Z]{2}[0-9]+$" };
    m(previewAssetTagScheme).mockResolvedValue(
      report({ scheme: regexScheme, preview: null, next_free: null }),
    );
    await renderLoaded();
    fireEvent.click(screen.getByTestId("asset-tag-regex-mode"));
    expect(screen.queryByTestId("asset-tag-prefix")).not.toBeInTheDocument();
    expect(screen.queryByTestId("asset-tag-sample")).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId("asset-tag-pattern"), {
      target: { value: "^[A-Z]{2}[0-9]+$" },
    });
    await waitFor(() =>
      expect(previewAssetTagScheme).toHaveBeenLastCalledWith(regexScheme),
    );
    await waitFor(() =>
      expect(screen.getByTestId("asset-tag-next-free")).toHaveTextContent("-"),
    );
  });

  test("is read-only without the Manage Asset Tags role", async () => {
    m(hasPermission).mockResolvedValue(false);
    await renderLoaded();
    expect(hasPermission).toHaveBeenCalledWith("Manage Asset Tags");
    expect(screen.getByTestId("asset-tag-read-only")).toBeInTheDocument();
    expect(prefixInput()).toBeDisabled();
    expect(screen.getByTestId("asset-tag-regex-mode")).toBeDisabled();
    expect(screen.getByTestId("asset-tag-enforce")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  test("saves the draft and shows the new nonconforming report", async () => {
    const savedScheme = { ...SCHEME, enforce: true };
    m(previewAssetTagScheme).mockResolvedValue(report({ scheme: savedScheme }));
    m(saveAssetTagScheme).mockResolvedValue(
      report({ scheme: savedScheme, nonconforming: ["legacy"] }),
    );
    await renderLoaded();
    fireEvent.click(screen.getByTestId("asset-tag-enforce"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Asset tag scheme saved.")).toBeInTheDocument();
    expect(saveAssetTagScheme).toHaveBeenCalledWith(savedScheme);
    expect(
      screen.getByText("1 of 10 existing tags do not conform to the saved scheme."),
    ).toBeInTheDocument();
    // Saving cancels the pending preview of the same draft.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 350));
    });
    expect(previewAssetTagScheme).not.toHaveBeenCalled();
  });

  test("a 422 on save marks the named fields invalid", async () => {
    m(saveAssetTagScheme).mockRejectedValue({
      response: {
        status: 422,
        data: { detail: { code: "invalid_scheme", fields: ["prefix", "suffix"] } },
      },
    });
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/Fix the highlighted fields/)).toBeInTheDocument();
    expect(prefixInput()).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByTestId("asset-tag-suffix")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getAllByText("This value is not valid for the scheme.")).toHaveLength(2);
  });

  test("any other save failure shows a generic error", async () => {
    m(saveAssetTagScheme).mockRejectedValue(new Error("boom"));
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText("Could not save the asset tag scheme."),
    ).toBeInTheDocument();
    expect(prefixInput()).toHaveAttribute("aria-invalid", "false");
  });
});

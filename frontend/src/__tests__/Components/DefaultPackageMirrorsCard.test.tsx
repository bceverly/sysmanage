// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { vi, describe, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(`{{${k}}}`, String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/repositoryMirroring", () => ({
  listDefaultMirrorAssignments: vi.fn(),
  setDefaultMirrorAssignment: vi.fn(),
}));

vi.mock("../../hooks/useModuleLicensed", () => ({
  useModuleLicensed: vi.fn(),
}));

import {
  listDefaultMirrorAssignments,
  setDefaultMirrorAssignment,
  HostDefaultMirrorRow,
} from "../../Services/repositoryMirroring";
import { useModuleLicensed } from "../../hooks/useModuleLicensed";
import DefaultPackageMirrorsCard from "../../Components/DefaultPackageMirrorsCard";

const mockList = vi.mocked(listDefaultMirrorAssignments);
const mockSet = vi.mocked(setDefaultMirrorAssignment);
const mockLicensed = vi.mocked(useModuleLicensed);

const ROWS = [
  {
    platform: "ubuntu",
    version_key: "24.04",
    os_family: "debian",
    label: "Ubuntu 24.04",
    match_regex: ".*",
    eligible_mirrors: [{ id: "m1", name: "Local Ubuntu Mirror" }],
    current_mirror_id: null,
    assignment_id: null,
    updated_at: null,
  },
  {
    platform: "fedora",
    version_key: "40",
    os_family: "redhat",
    label: "Fedora 40",
    match_regex: ".*",
    eligible_mirrors: [],
    current_mirror_id: null,
    assignment_id: null,
    updated_at: null,
  },
] as unknown as HostDefaultMirrorRow[];

const SUBTITLE_RE = /For each supported \(platform, version\) pair/;

const openFirstSelect = () => {
  const combos = screen.getAllByRole("combobox");
  fireEvent.mouseDown(combos[0]);
  return screen.getByRole("listbox");
};

describe("DefaultPackageMirrorsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLicensed.mockReturnValue(true);
    mockList.mockResolvedValue(ROWS);
    mockSet.mockResolvedValue({
      platform: "ubuntu",
      version_key: "24.04",
      os_family: "debian",
      mirror_id: "m1",
      previous_mirror_id: null,
      dispatched: [
        { host_id: "h1", message_id: "x1" },
        { host_id: "h2", message_id: "x2" },
      ],
    });
  });

  test("renders nothing when repository mirroring is unlicensed", () => {
    mockLicensed.mockReturnValue(false);
    const { container } = render(<DefaultPackageMirrorsCard />);
    expect(container).toBeEmptyDOMElement();
    expect(mockList).not.toHaveBeenCalled();
  });

  test("lists one row per catalog entry with its eligible mirrors", async () => {
    render(<DefaultPackageMirrorsCard />);
    expect(await screen.findByText("Default Package Mirrors")).toBeInTheDocument();
    expect(screen.getByText(SUBTITLE_RE)).toBeInTheDocument();
    expect(screen.getByText("Ubuntu 24.04")).toBeInTheDocument();
    expect(screen.getByText("Fedora 40")).toBeInTheDocument();
    expect(screen.getByText("No synced mirrors available")).toBeInTheDocument();
    const listbox = openFirstSelect();
    expect(within(listbox).getByText("Cloud (upstream default)")).toBeInTheDocument();
    expect(within(listbox).getByText("Local Ubuntu Mirror")).toBeInTheDocument();
  });

  test("assigning a mirror saves it, reports dispatch count and reloads", async () => {
    render(<DefaultPackageMirrorsCard />);
    await screen.findByText("Ubuntu 24.04");
    const listbox = openFirstSelect();
    fireEvent.click(within(listbox).getByText("Local Ubuntu Mirror"));
    await waitFor(() =>
      expect(mockSet).toHaveBeenCalledWith("ubuntu", "24.04", "debian", "m1"),
    );
    expect(
      await screen.findByText("Saved. 2 host(s) will be reconfigured."),
    ).toBeInTheDocument();
    expect(mockList).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() =>
      expect(screen.queryByText(/host\(s\) will be reconfigured/)).toBeNull(),
    );
  });

  test("choosing cloud reverts the assignment with a null mirror", async () => {
    mockList.mockResolvedValue([{ ...ROWS[0], current_mirror_id: "m1" }]);
    render(<DefaultPackageMirrorsCard />);
    await screen.findByText("Ubuntu 24.04");
    const listbox = openFirstSelect();
    fireEvent.click(within(listbox).getByText("Cloud (upstream default)"));
    await waitFor(() =>
      expect(mockSet).toHaveBeenCalledWith("ubuntu", "24.04", "debian", null),
    );
  });

  test("shows a save error and lets it be dismissed", async () => {
    mockSet.mockRejectedValue(new Error("mirror not synced"));
    render(<DefaultPackageMirrorsCard />);
    await screen.findByText("Ubuntu 24.04");
    const listbox = openFirstSelect();
    fireEvent.click(within(listbox).getByText("Local Ubuntu Mirror"));
    expect(await screen.findByText("mirror not synced")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() => expect(screen.queryByText("mirror not synced")).toBeNull());
  });

  test("stringifies a non-Error save failure", async () => {
    mockSet.mockRejectedValue("plain failure");
    render(<DefaultPackageMirrorsCard />);
    await screen.findByText("Ubuntu 24.04");
    const listbox = openFirstSelect();
    fireEvent.click(within(listbox).getByText("Local Ubuntu Mirror"));
    expect(await screen.findByText("plain failure")).toBeInTheDocument();
  });

  test("shows a load error from an Error", async () => {
    mockList.mockRejectedValue(new Error("402 payment required"));
    render(<DefaultPackageMirrorsCard />);
    expect(await screen.findByText("402 payment required")).toBeInTheDocument();
  });

  test("shows a load error from a non-Error value", async () => {
    mockList.mockRejectedValue("nope");
    render(<DefaultPackageMirrorsCard />);
    expect(await screen.findByText("nope")).toBeInTheDocument();
  });
});

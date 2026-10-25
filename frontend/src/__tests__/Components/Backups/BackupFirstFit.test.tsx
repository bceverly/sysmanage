// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A host's first backup against the target's free space: the estimate when
// it fits, the warning and the largest folders when it does not.

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

import { FirstFitCaption, FirstFitNote } from "../../../Components/Backups/BackupFirstFit";

const GB = 1e9;
const fit = (fits: boolean) => ({
  estimate_bytes: 40 * GB,
  available_bytes: (fits ? 90 : 10) * GB,
  fits,
  largest: [{ path: "/home/u", bytes: 38 * GB }, { path: "/var/lib", bytes: 1 * GB }],
});

describe("BackupFirstFit", () => {
  test("a first backup that fits shows its estimate only", () => {
    render(<><FirstFitNote fit={fit(true)} /><FirstFitCaption fit={fit(true)} /></>);
    expect(screen.getByText(/First backup: about/)).toBeInTheDocument();
    expect(screen.queryByText("First backup may not fit")).not.toBeInTheDocument();
  });

  test("one that does not fit says so and lists the largest folders", () => {
    render(<><FirstFitNote fit={fit(false)} /><FirstFitCaption fit={fit(false)} /></>);
    expect(screen.getByText(/may not fit: about/)).toBeInTheDocument();
    expect(screen.getByText(/^\/home\/u - /)).toBeInTheDocument();
    expect(screen.getByText("First backup may not fit")).toBeInTheDocument();
  });

  test("nothing to compare shows nothing", () => {
    const { container } = render(<><FirstFitNote fit={null} /><FirstFitCaption fit={null} /></>);
    expect(container).toBeEmptyDOMElement();
  });
});

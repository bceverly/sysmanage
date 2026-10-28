// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Grandfather-father-son retention (ROADMAP 24.6): set with the Pro+ backup
// engine, read-only without it, and a preview of what the next prune removes.

import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
const licensed = vi.hoisted(() => ({ value: true }));
vi.mock("../../../hooks/useModuleLicensed", () => ({
  useModuleLicensed: () => licensed.value,
  default: () => licensed.value,
}));
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, previewRetention: vi.fn() };
});

import { previewRetention } from "../../../Services/backups";
import RetentionFields from "../../../Components/Backups/RetentionFields";

const counts = { keep_last: 7, keep_daily: 7, keep_weekly: 4, keep_monthly: 6 };

describe("RetentionFields", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    licensed.value = true;
  });

  test("offers daily, weekly and monthly counts with the engine", () => {
    render(<RetentionFields hostId="h1" hasPolicy counts={counts} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Days to keep")).toHaveValue(7);
    expect(screen.getByLabelText("Weeks to keep")).toHaveValue(4);
    expect(screen.getByLabelText("Months to keep")).toHaveValue(6);
  });

  test("passes a changed count up", () => {
    const onChange = vi.fn();
    render(<RetentionFields hostId="h1" hasPolicy counts={counts} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Weeks to keep"), { target: { value: "8" } });
    expect(onChange).toHaveBeenCalledWith({ keep_weekly: 8 });
  });

  test("previews what the next prune removes", async () => {
    vi.mocked(previewRetention).mockResolvedValue({
      kept: ["20261022T030000Z"],
      removed: ["20261020T030000Z", "20261021T030000Z"],
    });
    render(<RetentionFields hostId="h1" hasPolicy counts={counts} onChange={vi.fn()} />);
    fireEvent.click(screen.getByText("Preview the next prune"));
    expect(await screen.findByText("Next prune: 1 kept, 2 removed.")).toBeInTheDocument();
    expect(screen.getByText("20261020T030000Z, 20261021T030000Z")).toBeInTheDocument();
    expect(previewRetention).toHaveBeenCalledWith("h1", counts);
  });

  test("without the engine an existing setting is shown read-only, and nothing otherwise", () => {
    licensed.value = false;
    const { container, rerender } = render(
      <RetentionFields hostId="h1" hasPolicy counts={counts} onChange={vi.fn()} />);
    expect(screen.getByText(/changing these needs Professional\+/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Days to keep")).toBeNull();
    rerender(<RetentionFields hostId="h1" hasPolicy
      counts={{ keep_last: 7, keep_daily: 0, keep_weekly: 0, keep_monthly: 0 }} onChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("years show only where the storage host can keep them, or when already set", () => {
    const { rerender } = render(
      <RetentionFields hostId="h1" hasPolicy counts={counts} onChange={vi.fn()} />);
    expect(screen.queryByLabelText("Years to keep")).toBeNull();
    rerender(<RetentionFields hostId="h1" hasPolicy yearlySupported
      counts={{ ...counts, keep_yearly: 0 }} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Years to keep")).toHaveValue(0);
    rerender(<RetentionFields hostId="h1" hasPolicy
      counts={{ ...counts, keep_yearly: 3 }} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Years to keep")).toHaveValue(3);
  });

  test("a yearly count is passed up and previewed", async () => {
    const onChange = vi.fn();
    vi.mocked(previewRetention).mockResolvedValue({ kept: [], removed: [] });
    const withYears = { ...counts, keep_yearly: 2 };
    render(<RetentionFields hostId="h1" hasPolicy yearlySupported counts={withYears}
      onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Years to keep"), { target: { value: "5" } });
    expect(onChange).toHaveBeenCalledWith({ keep_yearly: 5 });
    fireEvent.click(screen.getByText("Preview the next prune"));
    expect(await screen.findByText("Next prune: 0 kept, 0 removed.")).toBeInTheDocument();
    expect(previewRetention).toHaveBeenCalledWith("h1", withYears);
  });

  test("without the engine an existing yearly count is still shown", () => {
    licensed.value = false;
    render(<RetentionFields hostId="h1" hasPolicy counts={{ ...counts, keep_yearly: 3 }}
      onChange={vi.fn()} />);
    expect(screen.getByText(/And of the last 3 years\./)).toBeInTheDocument();
  });
});

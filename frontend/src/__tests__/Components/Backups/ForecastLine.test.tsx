// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Pro+ capacity forecasting on the target card (ROADMAP 24.6).

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

import { ForecastLine } from "../../../Components/Backups/BackupStorageStatus";
import type { BackupTarget } from "../../../Services/backups";

const target = (forecast: BackupTarget["forecast"]) =>
  ({ forecast, space_low_percent: 85, space_critical_percent: 95 }) as unknown as BackupTarget;

describe("ForecastLine", () => {
  test("nothing without a forecast", () => {
    const { container } = render(<ForecastLine target={target(null)} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("growth and days to each mark", () => {
    render(<ForecastLine target={target({ growth_bytes_per_day: 10 * 1024 ** 3,
      days_to_low: 25, days_to_critical: 35, basis_days: 30 })} />);
    expect(screen.getByText(/Growing about 10\.00 GB a day \(last 30 days\); 85% in about 25 days, 95% in about 35 days/))
      .toBeInTheDocument();
  });

  test("a flat target names no days, a full one says reached", () => {
    const { rerender } = render(<ForecastLine target={target({ growth_bytes_per_day: 0,
      days_to_low: null, days_to_critical: null, basis_days: 12 })} />);
    expect(screen.getByText("Forecast: Not growing (last 12 days)")).toBeInTheDocument();
    rerender(<ForecastLine target={target({ growth_bytes_per_day: 5,
      days_to_low: 0, days_to_critical: 4, basis_days: 30 })} />);
    expect(screen.getByText(/85% reached, 95% in about 4 days/)).toBeInTheDocument();
  });
});

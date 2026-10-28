// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Scheduled verification (ROADMAP 24.6, Pro+): the cadence field, the host
// card's line and the hosts table's caption.

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

import {
  VerificationCaption,
  VerificationField,
  VerificationLine,
} from "../../../Components/Backups/VerificationStatus";
import type { Verification } from "../../../Services/backups";

const v = (state: Verification["state"], extra: Partial<Verification> = {}): Verification => ({
  interval_days: 30, state, last_good_at: null, last_status: null, last_at: null,
  last_message: null, ...extra,
});

describe("VerificationStatus", () => {
  beforeEach(() => {
    licensed.value = true;
  });

  test("the field sets the cadence with the engine", () => {
    const onChange = vi.fn();
    render(<VerificationField days={0} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Read the whole repository back every (days)"),
      { target: { value: "30" } });
    expect(onChange).toHaveBeenCalledWith(30);
  });

  test("without the engine a set cadence is read-only, and nothing otherwise", () => {
    licensed.value = false;
    const { container, rerender } = render(<VerificationField days={30} onChange={vi.fn()} />);
    expect(screen.getByText(/every 30 days \(changing this needs Professional\+\)/)).toBeInTheDocument();
    rerender(<VerificationField days={0} onChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("the card says nothing when off, and why when it failed", () => {
    const { container, rerender } = render(<VerificationLine verification={v("off")} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<VerificationLine verification={v("failed", { last_message: "pack 12 unreadable" })} />);
    expect(screen.getByText(/The last pass failed - pack 12 unreadable/)).toBeInTheDocument();
    rerender(<VerificationLine verification={v("unverified")} />);
    expect(screen.getByText(/Not verified yet/)).toBeInTheDocument();
  });

  test("the table caption appears only when attention is needed", () => {
    const { container, rerender } = render(<VerificationCaption verification={v("verified",
      { last_good_at: "2026-10-27T03:00:00" })} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<VerificationCaption verification={v("unverified",
      { last_good_at: "2026-09-01T03:00:00" })} />);
    expect(screen.getByText(/Not verified in 30 days/)).toBeInTheDocument();
  });
});

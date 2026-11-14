// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

// One `t` per module, never per render -- see UserDetail.test.tsx.
vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallback?: string,
    opts?: Record<string, unknown>,
  ) => {
    let s = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

import { NextDiscDialog } from "../../Components/AirgapCollectionsDialogs";
import {
  CollectionRun,
  IN_FLIGHT_STATUSES,
  RunStatusCell,
  isBurnSet,
  statusColor,
} from "../../Components/AirgapCollectionsHelpers";

const SET: CollectionRun = {
  id: "r1",
  iso_label: "weekly-set",
  media_size_bytes: 4_700_000_000,
  include_cve: true,
  include_compliance: true,
  status: "AWAITING_MEDIA",
  started_at: null,
  completed_at: null,
  error_message: null,
  cron_schedule: null,
  parent_run_id: null,
  created_at: null,
  burn_device: "/dev/sr0",
  disc_count: 3,
  burned_disc_count: 1,
};

describe("burning a disc set", () => {
  test("waiting for media is a warning that does not poll", () => {
    expect(statusColor("AWAITING_MEDIA")).toBe("warning");
    expect(IN_FLIGHT_STATUSES.has("AWAITING_MEDIA")).toBe(false);
    expect(IN_FLIGHT_STATUSES.has("BURNING")).toBe(true);
  });

  test("only a burn run of two or more discs is a set", () => {
    expect(isBurnSet(SET)).toBe(true);
    expect(isBurnSet({ ...SET, disc_count: 1 })).toBe(false);
    expect(isBurnSet({ ...SET, disc_count: null })).toBe(false);
    expect(isBurnSet({ ...SET, burn_device: null })).toBe(false);
  });

  test("the status cell says which disc is done and asks for a blank one", () => {
    render(<RunStatusCell row={SET} />);
    expect(screen.getByText("AWAITING_MEDIA")).toBeInTheDocument();
    expect(
      screen.getByText("Disc 1 of 3 burned. Load a blank disc."),
    ).toBeInTheDocument();
  });

  test("the status cell names the disc being burned", () => {
    render(<RunStatusCell row={{ ...SET, status: "BURNING" }} />);
    expect(screen.getByText("Disc 2 of 3")).toBeInTheDocument();
  });

  test("a single-disc burn has no disc caption", () => {
    render(
      <RunStatusCell row={{ ...SET, status: "BURNING", disc_count: 1 }} />,
    );
    expect(screen.queryByText(/Disc \d of/)).not.toBeInTheDocument();
  });

  test("a finished set has no disc caption", () => {
    render(
      <RunStatusCell
        row={{ ...SET, status: "COMPLETE", burned_disc_count: 3 }}
      />,
    );
    expect(screen.queryByText(/Disc \d of/)).not.toBeInTheDocument();
  });

  test("the next-disc dialog explains the swap and confirms the run", () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(
      <NextDiscDialog
        run={SET}
        submitting={false}
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    );
    expect(
      screen.getByText(
        "Disc 1 of 3 is burned and has been ejected from /dev/sr0. Label it as disc 1, put a blank disc in the drive, then confirm to burn disc 2.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Burn disc 2" }));
    expect(onConfirm).toHaveBeenCalledWith(SET);
    fireEvent.click(screen.getByRole("button", { name: "Not yet" }));
    expect(onClose).toHaveBeenCalled();
  });

  test("the next-disc dialog locks its buttons while confirming", () => {
    render(
      <NextDiscDialog
        run={SET}
        submitting
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Burn disc 2" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Not yet" })).toBeDisabled();
  });

  test("the next-disc dialog is closed without a run", () => {
    render(
      <NextDiscDialog
        run={null}
        submitting={false}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.queryByText("Load the next disc")).not.toBeInTheDocument();
  });
});

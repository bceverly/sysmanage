// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The dashboard Backups card: failed runs and broken (or critically full)
// storage are errors; overdue and incomplete runs are warnings.

import { describe, test, expect } from "vitest";
import { backupSummaryLevel, reasonLabel } from "../../../Components/Backups/backupLabels";

describe("backupSummaryLevel", () => {
  test.each([
    [{ ok: 3 }, false, "ok"],
    [{ ok: 2, overdue: 1 }, false, "warning"],
    [{ ok: 2, incomplete: 1 }, false, "warning"],
    [{ ok: 2, failed: 1 }, false, "error"],
    [{ ok: 3 }, true, "error"],
    [{ incomplete: 1, failed: 1 }, false, "error"],
  ])("counts %o, storage problem %s -> %s", (counts, problem, level) => {
    expect(backupSummaryLevel({ counts, target_problem: problem })).toBe(level);
  });
});

describe("reasonLabel", () => {
  test("a missing NFS client says what to install", () => {
    const t = ((_k: string, fallback: string) => fallback) as never;
    expect(reasonLabel(t, "missing_nfs_client")).toBe("Install the NFS client");
  });
});

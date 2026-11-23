// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The navbar shows its menubar only while it fits beside the logo and the
// toolbar (2026-11-21: at 1280 px the search button covered "Administration").

import { test, expect } from "vitest";
import { menubarFits, neededWidth } from "../../Components/useMenubarFits";

test("the menubar fits only with room to spare beside the logo and toolbar", () => {
  // 1280 px wide: logo 250, toolbar 330 leave 700 - 72 spare = 628.
  expect(menubarFits(1280, 250, 330, 620)).toBe(true);
  expect(menubarFits(1280, 250, 330, 640)).toBe(false); // English menu at 1280
  expect(menubarFits(1805, 250, 330, 640)).toBe(true);
  expect(menubarFits(1805, 250, 330, 930)).toBe(true);
  expect(menubarFits(1500, 250, 330, 930)).toBe(false); // Russian labels
});

test("its natural width is every trigger side by side plus the gaps", () => {
  const bar = document.createElement("div");
  bar.style.columnGap = "4px";
  for (const width of [80, 100, 120]) {
    const item = document.createElement("button");
    item.getBoundingClientRect = () => ({ width } as DOMRect);
    bar.appendChild(item);
  }
  expect(neededWidth(bar)).toBe(80 + 100 + 120 + 2 * 4);
});

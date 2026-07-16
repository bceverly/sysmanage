// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import type { SxProps, Theme } from '@mui/material';

// Shared styling for the two-pane left-nav rails (Settings + Host Detail) so
// they look and behave identically ("global" styling, one source of truth).
//
// Vertical space is at a premium and horizontal space is not on modern wide
// displays, so the category groups flow into TWO columns — this roughly halves
// the rail's height and avoids the vertical scrollbar in the common case.
// ``break-inside: avoid`` keeps each category + its items together in a column.
export const navRailContainerSx: SxProps<Theme> = {
  flexShrink: 0,
  width: 380,
  columnCount: 2,
  columnGap: 1.5, // tight gutter between the two columns to save horizontal space
  borderRight: 1,
  borderColor: 'divider',
  pr: 1,
  overflowY: 'auto', // safety net only; two columns should fit without it
};

export const navRailGroupSx: SxProps<Theme> = {
  mb: 1.5,
  breakInside: 'avoid',
};

// The (non-clickable) category header.
export const navRailGroupTitleSx: SxProps<Theme> = {
  pl: 1.5,
  opacity: 0.6,
  display: 'block',
};

// The clickable items sit indented PAST their category header.  ``pl`` is
// flipped to padding-right in RTL locales by the app's stylis-rtl plugin, so
// the indent stays on the reading-start side for BIDI.
export const navRailItemSx: SxProps<Theme> = {
  borderRadius: 1,
  py: 0.5,
  pl: 3,
};

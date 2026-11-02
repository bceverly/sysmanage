// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A backup window's start hour is stored and entered in UTC; this says what
// that is on the viewer's own clock, so nobody has to work out the offset
// (Bryan, 2026-11-02: a "7 UTC" window landed in his working hours).  The
// offset is today's, so after a daylight-saving change the hint moves while
// the stored UTC hour does not.

const WINDOW_HOURS = 6;

const clock = (hourUtc: number, locale: string, now: Date, timeZone?: string): string => {
    const at = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hourUtc));
    return at.toLocaleTimeString(locale, { hour: 'numeric', minute: '2-digit', timeZone });
};

/** The window ``{start, end}`` in local time, or null for no valid hour. */
export const localWindow = (
    hourUtc: number | null | undefined, locale: string, now: Date = new Date(), timeZone?: string,
): { start: string; end: string } | null => {
    if (hourUtc === null || hourUtc === undefined || !Number.isInteger(hourUtc)
        || hourUtc < 0 || hourUtc > 23) return null;
    return {
        start: clock(hourUtc, locale, now, timeZone),
        end: clock((hourUtc + WINDOW_HOURS) % 24, locale, now, timeZone),
    };
};

/**
 * Utility functions for handling backend timestamps.
 *
 * The backend stores all datetimes as offset-naive UTC. When JavaScript's
 * Date constructor receives a string without the "Z" suffix (e.g.
 * "2025-01-15T14:30:00"), it interprets it as local time rather than UTC.
 * These utilities ensure timestamps are correctly parsed as UTC and
 * displayed in the user's local timezone.
 */

/**
 * Parse a backend timestamp string into a Date object, treating it as UTC.
 * Appends "Z" if not already present so `new Date()` correctly treats
 * the value as UTC.
 */
export const parseUTCTimestamp = (timestamp: string | null | undefined): Date | null => {
  if (!timestamp) return null;
  try {
    // If the timestamp already has timezone info (Z, +00:00, -05:00 etc.),
    // use it as-is.  Otherwise append "Z" so the browser treats it as UTC.
    const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(timestamp);
    const utcString = hasTimezone ? timestamp : timestamp + 'Z';
    const date = new Date(utcString);
    if (Number.isNaN(date.getTime())) return null;
    return date;
  } catch {
    return null;
  }
};

/**
 * Format a backend UTC timestamp for display in the user's local timezone.
 * Returns full date and time (e.g. "1/15/2025, 9:30:00 AM").
 */
export const formatUTCTimestamp = (timestamp: string | null | undefined, fallback = '-'): string => {
  const date = parseUTCTimestamp(timestamp);
  return date ? date.toLocaleString() : fallback;
};

/**
 * Format a backend UTC timestamp for display as date only.
 * Returns date portion (e.g. "1/15/2025").
 */
export const formatUTCDate = (timestamp: string | null | undefined, fallback = '-'): string => {
  const date = parseUTCTimestamp(timestamp);
  return date ? date.toLocaleDateString() : fallback;
};

/**
 * Format a backend UTC timestamp for display as time only.
 * Returns time portion (e.g. "9:30:00 AM").
 */
export const formatUTCTime = (timestamp: string | null | undefined, fallback = '-'): string => {
  const date = parseUTCTimestamp(timestamp);
  return date ? date.toLocaleTimeString() : fallback;
};

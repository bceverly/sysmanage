// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Clipboard helper that works in BOTH secure and non-secure browsing contexts.
 *
 * `navigator.clipboard` is only defined in a *secure context* (HTTPS or
 * localhost).  When SysManage is reached over plain HTTP by IP — common for a
 * freshly-installed server before TLS is set up — `navigator.clipboard` is
 * `undefined`, so `writeText()` throws and the copy silently fails.  This was
 * the bug behind the Server Role / Air-Gap "Copy" buttons doing nothing.
 *
 * Strategy: use the async Clipboard API when it's actually available, otherwise
 * fall back to the legacy hidden-`<textarea>` + `document.execCommand('copy')`
 * path, which works everywhere a user gesture is present (all callers here are
 * onClick handlers).
 *
 * Returns `true` if the text reached the clipboard, `false` if every strategy
 * failed — callers should surface an error on `false`.
 */
export async function copyToClipboard(value: string): Promise<boolean> {
  const nav = globalThis.navigator;
  if (typeof nav?.clipboard?.writeText === "function") {
    try {
      await nav.clipboard.writeText(value);
      return true;
    } catch {
      // Secure-context check passed but the write was rejected (permissions,
      // focus, etc.) — fall through to the legacy path.
    }
  }
  return legacyCopy(value);
}

// `document.execCommand('copy')` is the ONLY clipboard write available in a
// non-secure context (plain HTTP by IP), where `navigator.clipboard` is
// undefined — so the deprecated API is a deliberate, last-resort fallback.
// Reference it through a local interface (without the lib's `@deprecated` tag)
// so it doesn't trip deprecation lint while remaining typed.
interface LegacyClipboardDocument {
  body: HTMLElement | null;
  execCommand(commandId: string): boolean;
}

function legacyCopy(value: string): boolean {
  const doc = globalThis.document as unknown as LegacyClipboardDocument | undefined;
  if (!doc?.body || typeof doc.execCommand !== "function") {
    return false;
  }
  const textarea = globalThis.document.createElement("textarea");
  textarea.value = value;
  // Keep it off-screen so there's no scroll jump or mobile zoom on focus.
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  textarea.setAttribute("readonly", "");
  doc.body.appendChild(textarea);
  try {
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, value.length);
    return doc.execCommand("copy");
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}

# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Sanitize untrusted values before interpolating them into log messages.

Logging request-derived strings verbatim allows **log injection / log forging**
(CWE-117): an attacker who controls the value can embed CR/LF and forge
additional log lines (e.g. fake "login succeeded" entries) or break log
parsers.  :func:`scrub` removes the line-break characters — the fix CodeQL's
``py/log-injection`` query recognizes — and caps length so any request-derived
value (tenant ids, slugs, setting keys, names) is safe to log.

Use it on the *untrusted* argument only; static format strings and
developer-controlled tokens don't need it::

    logger.info("Provisioning tenant %s", scrub(tenant_id))
"""

_MAX_LOGGED_LEN = 256


def scrub(value, max_length: int = _MAX_LOGGED_LEN) -> str:
    """Return ``value`` as a single-line, length-capped string safe for logs.

    Strips CR/LF (the log-forging vectors) and tabs, and truncates over-long
    values so a hostile input can't flood the log.
    """
    text = str(value).replace("\r", "").replace("\n", "").replace("\t", " ")
    if len(text) > max_length:
        text = text[:max_length] + "…(truncated)"
    return text

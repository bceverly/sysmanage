# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

import gettext
import os
from typing import Optional

# Default language
DEFAULT_LANGUAGE = "en"

# Current language (can be changed at runtime)
CURRENT_LANGUAGE = DEFAULT_LANGUAGE

# Cache for loaded translation objects
TRANSLATIONS = {}


def set_language(language: str) -> None:
    """Set the current language for translations."""
    global CURRENT_LANGUAGE  # pylint: disable=global-statement
    CURRENT_LANGUAGE = language


def get_language() -> str:
    """Get the current language."""
    return CURRENT_LANGUAGE


def get_translation(language: Optional[str] = None) -> gettext.GNUTranslations:
    """Get translation object for the specified language."""
    if language is None:
        language = CURRENT_LANGUAGE

    if language not in TRANSLATIONS:
        try:
            # Get the directory containing this file
            localedir = os.path.join(os.path.dirname(__file__), "locales")
            translation = gettext.translation("messages", localedir, [language])
            TRANSLATIONS[language] = translation
        except FileNotFoundError:
            # Fall back to no translation (English)
            TRANSLATIONS[language] = gettext.NullTranslations()

    return TRANSLATIONS[language]


def _(message: str, language: Optional[str] = None) -> str:
    """Translate a message."""
    translation = get_translation(language)
    return translation.gettext(message)


def ngettext(
    singular: str, plural: str, count: int, language: Optional[str] = None
) -> str:
    """Translate a message with plural forms."""
    translation = get_translation(language)
    return translation.ngettext(singular, plural, count)


def module_translation(domain: str, localedir: str):
    """Return a ``_``-style translator bound to a Pro+ module's OWN catalog.

    Pro+ engine modules are compiled ``.so`` files downloaded from the license
    server; their translatable strings live in a gettext catalog that ships in
    the plugin bundle at ``<localedir>/<lang>/LC_MESSAGES/<domain>.mo`` — NOT in
    the OSS ``messages`` domain compiled into this server.  The returned callable
    resolves each string against THAT catalog using the server's current request
    language (the same ``set_language`` state the core ``_()`` uses), so a module
    string is localised per-request exactly like a core string.  Translations are
    cached per language.  Missing catalog/locale falls back to the English
    source, so an un-translated or absent module catalog is safe (never raises).

    The module loader injects the result after import (see ModuleLoader); a
    module declares an English-identity default so it also works standalone::

        _ = lambda s: s                     # default in the module
        def set_translator(fn): global _; _ = fn
        ...
        _("Apply security updates immediately")
    """
    cache: dict = {}

    def _translate(message: str, language: Optional[str] = None) -> str:
        lang = language if language is not None else CURRENT_LANGUAGE
        translation = cache.get(lang)
        if translation is None:
            try:
                translation = gettext.translation(domain, localedir, [lang])
            except OSError:  # FileNotFoundError is an OSError subclass
                translation = gettext.NullTranslations()
            cache[lang] = translation
        return translation.gettext(message)

    return _translate

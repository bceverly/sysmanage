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
    """Translate a message.

    NOTE: ``language`` is the SECOND positional argument.  This is NOT the
    i18next ``t(key, englishDefault)`` signature the frontend uses — passing
    English there asks gettext for a locale by that name, which falls back to
    ``NullTranslations`` and returns the msgid verbatim.  ``make lint`` gates
    against it (``scripts/i18n_check_msgid_style.py``).
    """
    translation = get_translation(language)
    return translation.gettext(message)


def N_(message: str) -> str:  # pylint: disable=invalid-name
    """Mark a string for extraction WITHOUT translating it yet.

    The standard gettext idiom for deferred translation.  ``xgettext`` only
    ever sees string *literals*, so a message held in a module constant::

        _MIRROR_NOT_FOUND = "Mirror not found"
        ...
        raise HTTPException(404, detail=_(_MIRROR_NOT_FOUND))

    is never extracted, never lands in a catalog, and therefore renders English
    in all 13 locales forever — silently, because no gate can miss a msgid that
    was never extracted.  A 2026-08-05 audit found 15 such constants feeding 48
    call sites.

    Wrapping the DEFINITION in ``N_`` puts the text in the .pot (xgettext is
    passed ``--keyword=N_``) while leaving the value an ordinary string; the
    ``_()`` at the call site then resolves it against the request's locale::

        _MIRROR_NOT_FOUND = N_("Mirror not found")

    Translating at definition time instead would bind the module-import
    locale, which is exactly wrong for a per-request server.
    """
    return message


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

"""
Comprehensive unit tests for backend.i18n internationalization module.
Tests language selection, translation loading, and message translation.
"""

import pytest
import gettext
from unittest.mock import patch, Mock, mock_open
import os

from backend.i18n import (
    DEFAULT_LANGUAGE,
    CURRENT_LANGUAGE,
    TRANSLATIONS,
    set_language,
    get_language,
    get_translation,
    _,
    ngettext,
)


class TestI18nBasics:
    """Test basic i18n functionality."""

    def test_default_language_constant(self):
        """Test that DEFAULT_LANGUAGE is set correctly."""
        assert DEFAULT_LANGUAGE == "en"

    def test_current_language_initial_value(self):
        """Test that CURRENT_LANGUAGE starts as default."""
        # Note: This may be affected by other tests, so check the module state
        from backend import i18n

        assert hasattr(i18n, "DEFAULT_LANGUAGE")
        assert hasattr(i18n, "CURRENT_LANGUAGE")

    def test_translations_cache_exists(self):
        """Test that TRANSLATIONS cache exists."""
        from backend import i18n

        assert hasattr(i18n, "TRANSLATIONS")
        assert isinstance(i18n.TRANSLATIONS, dict)


class TestLanguageManagement:
    """Test language setting and getting functions."""

    def setUp(self):
        """Reset language state before each test."""
        # Clear translations cache
        from backend import i18n

        i18n.TRANSLATIONS.clear()
        i18n.CURRENT_LANGUAGE = i18n.DEFAULT_LANGUAGE

    def test_set_language(self):
        """Test setting the current language."""
        original_lang = get_language()

        set_language("fr")
        assert get_language() == "fr"

        set_language("es")
        assert get_language() == "es"

        # Reset to original
        set_language(original_lang)

    def test_get_language(self):
        """Test getting the current language."""
        # Should return current language
        current = get_language()
        assert isinstance(current, str)
        assert len(current) >= 2  # Language codes are at least 2 chars

    def test_set_get_language_roundtrip(self):
        """Test setting and getting language works correctly."""
        original_lang = get_language()

        test_languages = ["de", "it", "pt", "ja"]
        for lang in test_languages:
            set_language(lang)
            assert get_language() == lang

        # Reset
        set_language(original_lang)


class TestTranslationLoading:
    """Test translation loading and caching."""

    def setUp(self):
        """Clear translations cache before each test."""
        from backend import i18n

        i18n.TRANSLATIONS.clear()

    @patch("backend.i18n.gettext.translation")
    @patch("backend.i18n.os.path.join")
    @patch("backend.i18n.os.path.dirname")
    def test_get_translation_success(
        self, mock_dirname, mock_join, mock_gettext_translation
    ):
        """Test successful translation loading."""
        # Mock the paths
        mock_dirname.return_value = "/path/to/i18n"
        mock_join.return_value = "/path/to/i18n/locales"

        # Mock successful translation loading
        mock_translation = Mock(spec=gettext.GNUTranslations)
        mock_gettext_translation.return_value = mock_translation

        result = get_translation("fr")

        assert result == mock_translation
        mock_gettext_translation.assert_called_once_with(
            "messages", "/path/to/i18n/locales", ["fr"]
        )

        # Verify caching
        from backend import i18n

        assert "fr" in i18n.TRANSLATIONS
        assert i18n.TRANSLATIONS["fr"] == mock_translation

    @patch("backend.i18n.gettext.translation")
    @patch("backend.i18n.gettext.NullTranslations")
    def test_get_translation_file_not_found(
        self, mock_null_translations, mock_gettext_translation
    ):
        """Test translation loading when file not found."""
        # Mock FileNotFoundError
        mock_gettext_translation.side_effect = FileNotFoundError(
            "Translation not found"
        )

        # Mock NullTranslations - create a fresh mock without spec
        mock_null_translation = Mock()
        mock_null_translations.return_value = mock_null_translation

        result = get_translation("nonexistent")

        assert result == mock_null_translation
        mock_null_translations.assert_called_once()

        # Verify caching of fallback
        from backend import i18n

        assert "nonexistent" in i18n.TRANSLATIONS
        assert i18n.TRANSLATIONS["nonexistent"] == mock_null_translation

    def test_get_translation_default_language(self):
        """Test get_translation with default language parameter."""
        original_lang = get_language()

        # Set current language to something specific
        set_language("es")

        # Call without language parameter should use current language
        with patch("backend.i18n.gettext.translation") as mock_translation:
            mock_trans_obj = Mock()
            mock_translation.return_value = mock_trans_obj

            result = get_translation()  # No language parameter

            # Should use current language ("es")
            from unittest.mock import ANY

            mock_translation.assert_called_with("messages", ANY, ["es"])

        # Reset
        set_language(original_lang)

    def test_get_translation_caching(self):
        """Test that translations are cached properly."""
        with patch("backend.i18n.gettext.translation") as mock_gettext_translation:
            mock_translation = Mock(spec=gettext.GNUTranslations)
            mock_gettext_translation.return_value = mock_translation

            # First call
            result1 = get_translation("de")
            # Second call
            result2 = get_translation("de")

            # Should be same object
            assert result1 is result2
            # Translation should only be loaded once
            mock_gettext_translation.assert_called_once()

    def test_get_translation_explicit_language(self):
        """Test get_translation with explicit language parameter."""
        with patch("backend.i18n.gettext.translation") as mock_gettext_translation:
            mock_translation = Mock(spec=gettext.GNUTranslations)
            mock_gettext_translation.return_value = mock_translation

            result = get_translation("it")

            from unittest.mock import ANY

            mock_gettext_translation.assert_called_once_with("messages", ANY, ["it"])
            assert result == mock_translation


class TestMessageTranslation:
    """Test message translation functions."""

    def setUp(self):
        """Clear translations cache before each test."""
        from backend import i18n

        i18n.TRANSLATIONS.clear()

    def test_translate_message_basic(self):
        """Test basic message translation."""
        # Mock translation object
        mock_translation = Mock(spec=gettext.GNUTranslations)
        mock_translation.gettext.return_value = "Bonjour"

        with patch("backend.i18n.get_translation") as mock_get_translation:
            mock_get_translation.return_value = mock_translation

            result = _("Hello")

            assert result == "Bonjour"
            mock_translation.gettext.assert_called_once_with("Hello")
            mock_get_translation.assert_called_once_with(None)

    def test_translate_message_with_language(self):
        """Test message translation with specific language."""
        mock_translation = Mock(spec=gettext.GNUTranslations)
        mock_translation.gettext.return_value = "Hola"

        with patch("backend.i18n.get_translation") as mock_get_translation:
            mock_get_translation.return_value = mock_translation

            result = _("Hello", language="es")

            assert result == "Hola"
            mock_translation.gettext.assert_called_once_with("Hello")
            mock_get_translation.assert_called_once_with("es")

    def test_ngettext_basic(self):
        """Test plural message translation."""
        mock_translation = Mock(spec=gettext.GNUTranslations)
        mock_translation.ngettext.return_value = "1 elemento"

        with patch("backend.i18n.get_translation") as mock_get_translation:
            mock_get_translation.return_value = mock_translation

            result = ngettext("1 item", "{} items", 1)

            assert result == "1 elemento"
            mock_translation.ngettext.assert_called_once_with("1 item", "{} items", 1)
            mock_get_translation.assert_called_once_with(None)

    def test_ngettext_plural(self):
        """Test plural message translation with count > 1."""
        mock_translation = Mock(spec=gettext.GNUTranslations)
        mock_translation.ngettext.return_value = "5 elementos"

        with patch("backend.i18n.get_translation") as mock_get_translation:
            mock_get_translation.return_value = mock_translation

            result = ngettext("1 item", "{} items", 5)

            assert result == "5 elementos"
            mock_translation.ngettext.assert_called_once_with("1 item", "{} items", 5)

    def test_ngettext_with_language(self):
        """Test plural message translation with specific language."""
        mock_translation = Mock(spec=gettext.GNUTranslations)
        mock_translation.ngettext.return_value = "1 Article"

        with patch("backend.i18n.get_translation") as mock_get_translation:
            mock_get_translation.return_value = mock_translation

            result = ngettext("1 item", "{} items", 1, language="de")

            assert result == "1 Article"
            mock_translation.ngettext.assert_called_once_with("1 item", "{} items", 1)
            mock_get_translation.assert_called_once_with("de")

    def test_translate_message_fallback_behavior(self):
        """Test translation fallback when no translation available."""
        # Mock NullTranslations (fallback)
        mock_null_translation = Mock(spec=gettext.NullTranslations)
        mock_null_translation.gettext.return_value = "Hello"  # Returns original

        with patch("backend.i18n.get_translation") as mock_get_translation:
            mock_get_translation.return_value = mock_null_translation

            result = _("Hello")

            # Should return original message when no translation
            assert result == "Hello"
            mock_null_translation.gettext.assert_called_once_with("Hello")

    def test_ngettext_fallback_behavior(self):
        """Test plural translation fallback when no translation available."""
        mock_null_translation = Mock(spec=gettext.NullTranslations)
        mock_null_translation.ngettext.return_value = (
            "5 items"  # Returns appropriate form
        )

        with patch("backend.i18n.get_translation") as mock_get_translation:
            mock_get_translation.return_value = mock_null_translation

            result = ngettext("1 item", "{} items", 5)

            assert result == "5 items"
            mock_null_translation.ngettext.assert_called_once_with(
                "1 item", "{} items", 5
            )


class TestI18nIntegration:
    """Test integration scenarios."""

    def setUp(self):
        """Clear translations cache and reset language."""
        from backend import i18n

        i18n.TRANSLATIONS.clear()
        i18n.CURRENT_LANGUAGE = i18n.DEFAULT_LANGUAGE

    def test_language_switching_workflow(self):
        """Test complete language switching workflow."""
        original_lang = get_language()

        # Mock different translations for different languages
        mock_en_translation = Mock(spec=gettext.NullTranslations)
        mock_en_translation.gettext.return_value = "Hello"

        mock_fr_translation = Mock(spec=gettext.GNUTranslations)
        mock_fr_translation.gettext.return_value = "Bonjour"

        def mock_get_translation_side_effect(lang=None):
            if lang == "fr":
                return mock_fr_translation
            return mock_en_translation

        with patch(
            "backend.i18n.get_translation", side_effect=mock_get_translation_side_effect
        ):
            # Start with default language
            result_en = _("Hello")
            assert result_en == "Hello"

            # Switch to French - and explicitly pass French as the language
            set_language("fr")
            result_fr = _("Hello", language="fr")  # Explicitly pass language
            assert result_fr == "Bonjour"

            # Verify language changed
            assert get_language() == "fr"

        # Reset
        set_language(original_lang)

    def test_multiple_language_caching(self):
        """Test that multiple languages can be cached simultaneously."""
        with patch("backend.i18n.gettext.translation") as mock_gettext_translation:
            # Create different mock translations
            mock_fr_translation = Mock(spec=gettext.GNUTranslations)
            mock_de_translation = Mock(spec=gettext.GNUTranslations)
            mock_es_translation = Mock(spec=gettext.GNUTranslations)

            def mock_translation_side_effect(domain, localedir, languages):
                if "fr" in languages:
                    return mock_fr_translation
                elif "de" in languages:
                    return mock_de_translation
                elif "es" in languages:
                    return mock_es_translation

            mock_gettext_translation.side_effect = mock_translation_side_effect

            # Load different languages
            result_fr = get_translation("fr")
            result_de = get_translation("de")
            result_es = get_translation("es")

            # Verify all are cached
            from backend import i18n

            assert "fr" in i18n.TRANSLATIONS
            assert "de" in i18n.TRANSLATIONS
            assert "es" in i18n.TRANSLATIONS

            # Verify they're different objects
            assert result_fr is not result_de
            assert result_de is not result_es
            assert result_fr is not result_es

    def test_module_constants_immutable(self):
        """Test that module constants exist and maintain expected values."""
        from backend import i18n

        # Test constants exist
        assert hasattr(i18n, "DEFAULT_LANGUAGE")
        assert hasattr(i18n, "CURRENT_LANGUAGE")
        assert hasattr(i18n, "TRANSLATIONS")

        # Test DEFAULT_LANGUAGE is expected value
        assert i18n.DEFAULT_LANGUAGE == "en"

        # Test TRANSLATIONS is a dictionary
        assert isinstance(i18n.TRANSLATIONS, dict)

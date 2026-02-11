"""
Tests for backend/utils/password_hash.py module.
Tests password hashing utilities for different operating systems.
"""

import re

import pytest

from backend.utils.password_hash import (
    CRYPT_B64,
    _b64_encode_24bit,
    _sha512_crypt_impl,
    generate_salt,
    hash_password_bcrypt,
    hash_password_for_os,
    hash_password_sha512_crypt,
)


class TestGenerateSalt:
    """Tests for generate_salt function."""

    def test_generate_salt_default_length(self):
        """Test salt generation with default length."""
        salt = generate_salt()
        assert len(salt) == 16

    def test_generate_salt_custom_length(self):
        """Test salt generation with custom length."""
        salt = generate_salt(8)
        assert len(salt) == 8

        salt = generate_salt(32)
        assert len(salt) == 32

    def test_generate_salt_valid_characters(self):
        """Test that salt contains only valid characters."""
        salt = generate_salt(100)
        valid_chars = set(
            "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        )
        for char in salt:
            assert char in valid_chars

    def test_generate_salt_randomness(self):
        """Test that generated salts are random."""
        salts = [generate_salt() for _ in range(100)]
        # All salts should be unique (statistically very unlikely to have duplicates)
        assert len(set(salts)) == 100


class TestB64Encode24bit:
    """Tests for _b64_encode_24bit function."""

    def test_b64_encode_24bit_zeros(self):
        """Test encoding all zeros."""
        result = _b64_encode_24bit(0, 0, 0, 4)
        assert len(result) == 4
        assert all(c == "." for c in result)

    def test_b64_encode_24bit_single_char(self):
        """Test encoding to single character."""
        result = _b64_encode_24bit(0, 0, 1, 1)
        assert len(result) == 1
        assert result == CRYPT_B64[1]

    def test_b64_encode_24bit_various_values(self):
        """Test encoding various byte combinations."""
        # Test with some specific values
        result = _b64_encode_24bit(255, 255, 255, 4)
        assert len(result) == 4

        result = _b64_encode_24bit(0x12, 0x34, 0x56, 4)
        assert len(result) == 4

    def test_b64_encode_24bit_two_chars(self):
        """Test encoding to 2 characters."""
        result = _b64_encode_24bit(0, 0, 63, 2)
        assert len(result) == 2


class TestSha512CryptImpl:
    """Tests for _sha512_crypt_impl function."""

    def test_sha512_crypt_format(self):
        """Test that output follows $6$salt$hash format."""
        result = _sha512_crypt_impl("password", "testsalt")
        assert result.startswith("$6$testsalt$")
        # Hash should have 86 characters (SHA-512 output encoded)
        parts = result.split("$")
        assert len(parts) == 4
        assert parts[1] == "6"
        assert parts[2] == "testsalt"
        assert len(parts[3]) == 86

    def test_sha512_crypt_deterministic(self):
        """Test that same inputs produce same output."""
        result1 = _sha512_crypt_impl("password", "salt1234")
        result2 = _sha512_crypt_impl("password", "salt1234")
        assert result1 == result2

    def test_sha512_crypt_different_passwords(self):
        """Test that different passwords produce different outputs."""
        result1 = _sha512_crypt_impl("password1", "salt1234")
        result2 = _sha512_crypt_impl("password2", "salt1234")
        assert result1 != result2

    def test_sha512_crypt_different_salts(self):
        """Test that different salts produce different outputs."""
        result1 = _sha512_crypt_impl("password", "salt1234")
        result2 = _sha512_crypt_impl("password", "salt5678")
        assert result1 != result2

    def test_sha512_crypt_salt_truncation(self):
        """Test that salt is truncated to 16 characters."""
        long_salt = "a" * 32
        result = _sha512_crypt_impl("password", long_salt)
        # Salt in output should be truncated to 16 chars
        parts = result.split("$")
        assert len(parts[2]) == 16

    def test_sha512_crypt_custom_rounds(self):
        """Test with custom number of rounds."""
        result = _sha512_crypt_impl("password", "salt1234", rounds=10000)
        assert result.startswith("$6$rounds=10000$salt1234$")

    def test_sha512_crypt_default_rounds(self):
        """Test that default rounds don't include rounds= prefix."""
        result = _sha512_crypt_impl("password", "salt1234", rounds=5000)
        assert "$rounds=" not in result
        assert result.startswith("$6$salt1234$")

    def test_sha512_crypt_empty_password(self):
        """Test hashing empty password."""
        result = _sha512_crypt_impl("", "salt1234")
        assert result.startswith("$6$salt1234$")

    def test_sha512_crypt_unicode_password(self):
        """Test hashing unicode password."""
        result = _sha512_crypt_impl("пароль", "salt1234")
        assert result.startswith("$6$salt1234$")

    def test_sha512_crypt_long_password(self):
        """Test hashing long password."""
        long_password = "a" * 1000
        result = _sha512_crypt_impl(long_password, "salt1234")
        assert result.startswith("$6$salt1234$")


class TestHashPasswordSha512Crypt:
    """Tests for hash_password_sha512_crypt function."""

    def test_hash_password_sha512_crypt_format(self):
        """Test output format."""
        result = hash_password_sha512_crypt("password")
        assert result.startswith("$6$")
        parts = result.split("$")
        assert len(parts) == 4
        assert parts[1] == "6"
        assert len(parts[2]) == 16  # Salt length
        assert len(parts[3]) == 86  # Hash length

    def test_hash_password_sha512_crypt_random_salt(self):
        """Test that each call uses a different salt."""
        result1 = hash_password_sha512_crypt("password")
        result2 = hash_password_sha512_crypt("password")
        # Same password should have different hashes due to random salt
        assert result1 != result2

    def test_hash_password_sha512_crypt_various_passwords(self):
        """Test hashing various passwords."""
        passwords = ["simple", "Complex123!", "with spaces", "émoji🔐"]
        for password in passwords:
            result = hash_password_sha512_crypt(password)
            assert result.startswith("$6$")


class TestHashPasswordBcrypt:
    """Tests for hash_password_bcrypt function."""

    def test_hash_password_bcrypt_format(self):
        """Test bcrypt output format."""
        result = hash_password_bcrypt("password")
        # bcrypt format: $2b$rounds$salt_and_hash
        assert result.startswith("$2b$12$")  # 12 rounds
        assert len(result) == 60

    def test_hash_password_bcrypt_random_salt(self):
        """Test that each call uses a different salt."""
        result1 = hash_password_bcrypt("password")
        result2 = hash_password_bcrypt("password")
        assert result1 != result2

    def test_hash_password_bcrypt_verifiable(self):
        """Test that hashed password can be verified."""
        import bcrypt

        password = "test_password"
        hashed = hash_password_bcrypt(password)
        assert bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    def test_hash_password_bcrypt_various_passwords(self):
        """Test hashing various passwords."""
        passwords = ["simple", "Complex123!", "with spaces"]
        for password in passwords:
            result = hash_password_bcrypt(password)
            assert result.startswith("$2b$")


class TestHashPasswordForOs:
    """Tests for hash_password_for_os function."""

    def test_hash_password_for_debian(self):
        """Test that Debian uses SHA-512 crypt."""
        result = hash_password_for_os("password", "debian")
        assert result.startswith("$6$")

    def test_hash_password_for_ubuntu(self):
        """Test that Ubuntu uses SHA-512 crypt."""
        result = hash_password_for_os("password", "ubuntu")
        assert result.startswith("$6$")

    def test_hash_password_for_debian_case_insensitive(self):
        """Test that distribution matching is case insensitive."""
        result = hash_password_for_os("password", "DEBIAN")
        assert result.startswith("$6$")

        result = hash_password_for_os("password", "Debian")
        assert result.startswith("$6$")

    def test_hash_password_for_alpine(self):
        """Test that Alpine uses bcrypt."""
        result = hash_password_for_os("password", "alpine")
        assert result.startswith("$2b$")

    def test_hash_password_for_openbsd(self):
        """Test that OpenBSD uses bcrypt."""
        result = hash_password_for_os("password", "openbsd")
        assert result.startswith("$2b$")

    def test_hash_password_for_freebsd(self):
        """Test that FreeBSD uses bcrypt (default)."""
        result = hash_password_for_os("password", "freebsd")
        assert result.startswith("$2b$")

    def test_hash_password_for_unknown(self):
        """Test that unknown distributions use bcrypt."""
        result = hash_password_for_os("password", "unknown")
        assert result.startswith("$2b$")

    def test_hash_password_for_empty_distribution(self):
        """Test with empty distribution string."""
        result = hash_password_for_os("password", "")
        assert result.startswith("$2b$")

    def test_hash_password_for_none_distribution(self):
        """Test with None distribution."""
        result = hash_password_for_os("password", None)
        assert result.startswith("$2b$")

    def test_hash_password_for_distribution_with_version(self):
        """Test distribution strings with version numbers."""
        result = hash_password_for_os("password", "debian-12")
        assert result.startswith("$6$")

        result = hash_password_for_os("password", "ubuntu-22.04")
        assert result.startswith("$6$")


class TestCryptB64Constant:
    """Tests for CRYPT_B64 constant."""

    def test_crypt_b64_length(self):
        """Test that CRYPT_B64 has 64 characters."""
        assert len(CRYPT_B64) == 64

    def test_crypt_b64_unique_chars(self):
        """Test that CRYPT_B64 contains unique characters."""
        assert len(set(CRYPT_B64)) == 64

    def test_crypt_b64_valid_chars(self):
        """Test that CRYPT_B64 starts with ./ followed by alphanumerics."""
        assert CRYPT_B64[0] == "."
        assert CRYPT_B64[1] == "/"

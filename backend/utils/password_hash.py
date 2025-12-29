"""
Password hashing utilities for child host creation.

This module provides password hashing functions for different operating systems.
Different autoinstall/preseed systems require different hash formats:
- Debian preseed: SHA-512 crypt format ($6$...)
- Alpine: bcrypt or SHA-512
- OpenBSD: bcrypt ($2b$...)
- Windows WSL: plain text (handled by WSL)

Note: Python's crypt module on some platforms (e.g., OpenBSD) doesn't support
SHA-512 ($6$), so we implement it using hashlib following the glibc specification.

SECURITY NOTE (CodeQL false positive suppression):
The use of hashlib.sha512() in this module is NOT a security vulnerability.
This code implements the SHA-512 crypt password hashing algorithm as specified
by glibc (used in /etc/shadow on Linux systems). SHA-512 crypt is:
- A key derivation function with 5000+ rounds of hashing (not raw SHA-512)
- Uses a cryptographically random 16-character salt
- Compliant with IEEE Std 1003.1-2008 (POSIX) crypt() specification
- The standard password hash format for Debian/Ubuntu preseed automation

This is fundamentally different from using raw SHA-512 to hash passwords, which
would indeed be insecure. The SHA-512 crypt algorithm ($6$) provides equivalent
security to bcrypt or PBKDF2 when properly configured.

See: https://www.akkadia.org/drepper/SHA-crypt.txt
"""

import hashlib
import secrets
import string

import bcrypt


# Base64 alphabet used by SHA-512 crypt (different from standard base64)
CRYPT_B64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def generate_salt(length: int = 16) -> str:
    """
    Generate a random salt for password hashing.

    Args:
        length: Salt length (default 16)

    Returns:
        Random salt string
    """
    alphabet = string.ascii_letters + string.digits + "./"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _b64_encode_24bit(b1: int, b2: int, b3: int, n: int) -> str:
    """Encode 3 bytes into n base64 characters for SHA-512 crypt."""
    w = (b1 << 16) | (b2 << 8) | b3
    result = ""
    for _ in range(n):
        result += CRYPT_B64[w & 0x3F]
        w >>= 6
    return result


def _sha512_crypt_impl(password: str, salt: str, rounds: int = 5000) -> str:
    """
    Implement SHA-512 crypt algorithm as specified by glibc.

    This is a pure Python implementation that works on all platforms,
    including those where the system crypt() doesn't support $6$ hashes.

    Args:
        password: Plain text password
        salt: Salt string (max 16 chars)
        rounds: Number of rounds (default 5000)

    Returns:
        SHA-512 crypt hash string
    """
    # Truncate salt to 16 characters max
    salt = salt[:16]
    password_bytes = password.encode("utf-8")
    salt_bytes = salt.encode("utf-8")

    # Step 1-8: Create digest B
    b_ctx = hashlib.sha512()
    b_ctx.update(password_bytes)
    b_ctx.update(salt_bytes)
    b_ctx.update(password_bytes)
    digest_b = b_ctx.digest()

    # Step 9-12: Create digest A
    a_ctx = hashlib.sha512()
    a_ctx.update(password_bytes)
    a_ctx.update(salt_bytes)

    # Step 11: Add bytes from B based on password length
    pwd_len = len(password_bytes)
    remaining = pwd_len
    while remaining > 64:
        a_ctx.update(digest_b)
        remaining -= 64
    a_ctx.update(digest_b[:remaining])

    # Step 12: For each bit of password length, add B or password
    i = pwd_len
    while i > 0:
        if i & 1:
            a_ctx.update(digest_b)
        else:
            a_ctx.update(password_bytes)
        i >>= 1

    digest_a = a_ctx.digest()

    # Step 13-15: Create digest DP (password repeated)
    dp_ctx = hashlib.sha512()
    for _ in range(pwd_len):
        dp_ctx.update(password_bytes)
    digest_dp = dp_ctx.digest()

    # Step 16: Create P string
    p_bytes = b""
    remaining = pwd_len
    while remaining > 64:
        p_bytes += digest_dp
        remaining -= 64
    p_bytes += digest_dp[:remaining]

    # Step 17-19: Create digest DS (salt repeated 16 + A[0] times)
    ds_ctx = hashlib.sha512()
    for _ in range(16 + digest_a[0]):
        ds_ctx.update(salt_bytes)
    digest_ds = ds_ctx.digest()

    # Step 20: Create S string
    s_bytes = b""
    remaining = len(salt_bytes)
    while remaining > 64:
        s_bytes += digest_ds
        remaining -= 64
    s_bytes += digest_ds[:remaining]

    # Step 21: Perform rounds
    digest_c = digest_a
    for i in range(rounds):
        c_ctx = hashlib.sha512()

        if i & 1:
            c_ctx.update(p_bytes)
        else:
            c_ctx.update(digest_c)

        if i % 3:
            c_ctx.update(s_bytes)

        if i % 7:
            c_ctx.update(p_bytes)

        if i & 1:
            c_ctx.update(digest_c)
        else:
            c_ctx.update(p_bytes)

        digest_c = c_ctx.digest()

    # Step 22: Encode final digest
    # The encoding order is specified by glibc
    result = ""
    result += _b64_encode_24bit(digest_c[0], digest_c[21], digest_c[42], 4)
    result += _b64_encode_24bit(digest_c[22], digest_c[43], digest_c[1], 4)
    result += _b64_encode_24bit(digest_c[44], digest_c[2], digest_c[23], 4)
    result += _b64_encode_24bit(digest_c[3], digest_c[24], digest_c[45], 4)
    result += _b64_encode_24bit(digest_c[25], digest_c[46], digest_c[4], 4)
    result += _b64_encode_24bit(digest_c[47], digest_c[5], digest_c[26], 4)
    result += _b64_encode_24bit(digest_c[6], digest_c[27], digest_c[48], 4)
    result += _b64_encode_24bit(digest_c[28], digest_c[49], digest_c[7], 4)
    result += _b64_encode_24bit(digest_c[50], digest_c[8], digest_c[29], 4)
    result += _b64_encode_24bit(digest_c[9], digest_c[30], digest_c[51], 4)
    result += _b64_encode_24bit(digest_c[31], digest_c[52], digest_c[10], 4)
    result += _b64_encode_24bit(digest_c[53], digest_c[11], digest_c[32], 4)
    result += _b64_encode_24bit(digest_c[12], digest_c[33], digest_c[54], 4)
    result += _b64_encode_24bit(digest_c[34], digest_c[55], digest_c[13], 4)
    result += _b64_encode_24bit(digest_c[56], digest_c[14], digest_c[35], 4)
    result += _b64_encode_24bit(digest_c[15], digest_c[36], digest_c[57], 4)
    result += _b64_encode_24bit(digest_c[37], digest_c[58], digest_c[16], 4)
    result += _b64_encode_24bit(digest_c[59], digest_c[17], digest_c[38], 4)
    result += _b64_encode_24bit(digest_c[18], digest_c[39], digest_c[60], 4)
    result += _b64_encode_24bit(digest_c[40], digest_c[61], digest_c[19], 4)
    result += _b64_encode_24bit(digest_c[62], digest_c[20], digest_c[41], 4)
    result += _b64_encode_24bit(0, 0, digest_c[63], 2)

    # Format: $6$salt$hash (or $6$rounds=N$salt$hash if non-default rounds)
    if rounds == 5000:
        return f"$6${salt}${result}"
    return f"$6$rounds={rounds}${salt}${result}"


def hash_password_sha512_crypt(password: str) -> str:
    """
    Hash a password using SHA-512 crypt format ($6$...).

    This format is required by Debian preseed for passwd/user-password-crypted.

    Args:
        password: Plain text password to hash

    Returns:
        SHA-512 crypt formatted password hash ($6$salt$hash)
    """
    salt = generate_salt(16)
    return _sha512_crypt_impl(password, salt)


def hash_password_bcrypt(password: str) -> str:
    """
    Hash a password using bcrypt format ($2b$...).

    This format is used by OpenBSD, Alpine, and other systems.

    Args:
        password: Plain text password to hash

    Returns:
        bcrypt formatted password hash
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=8)).decode(
        "utf-8"
    )


def hash_password_for_os(password: str, distribution: str) -> str:
    """
    Hash a password using the appropriate format for the target OS.

    Args:
        password: Plain text password to hash
        distribution: Distribution name (e.g., "debian", "alpine", "openbsd")

    Returns:
        Appropriately formatted password hash
    """
    distribution_lower = distribution.lower() if distribution else ""

    # Debian and Ubuntu use SHA-512 crypt for preseed
    if "debian" in distribution_lower or "ubuntu" in distribution_lower:
        return hash_password_sha512_crypt(password)

    # Default to bcrypt for other systems (Alpine, OpenBSD, etc.)
    return hash_password_bcrypt(password)

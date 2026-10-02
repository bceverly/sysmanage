# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The server's TLS cipher policy: AEAD only (Phase 22).

WHY
---
Lucky Thirteen (CVE-2013-0169) recovers plaintext from TLS records protected
by CBC-mode cipher suites, by timing how long the receiver takes to reject
tampered padding; its successors (Lucky Microseconds, the POODLE family)
attack the same MAC-then-encrypt CBC construction.  The fix that ends the
whole class is to offer no CBC suites at all.

Found 2026-10-02: the server offered them.  uvicorn's default cipher string
is ``"TLSv1"``, which hands the server ECDHE-RSA-AES128-SHA and the other CBC
suites (plus NULL and anonymous ones in its list); the installers' nginx
configs set ``ssl_protocols`` but no ``ssl_ciphers``, so nginx used its
default ``HIGH:!aNULL:!MD5`` -- CBC suites again, under TLS 1.2.

THE POLICY
----------
TLS 1.3 suites are all AEAD and are not affected by this list.  For TLS 1.2
only AES-GCM and ChaCha20-Poly1305 with forward secrecy (ECDHE, DHE) -- the
TLS 1.2 half of Mozilla's "intermediate" profile.  TLS 1.0 and 1.1 have no
AEAD suites, so this list also closes them.  Every agent build since TLS 1.2
became the floor negotiates one of these.

The same string is in every installer's ``sysmanage-nginx.conf``;
``tests/test_tls_lucky13.py`` (its own CI step) holds both to it and makes
real handshakes against the context uvicorn builds.
"""

SERVER_CIPHERS = ":".join(
    (
        "ECDHE-ECDSA-AES128-GCM-SHA256",
        "ECDHE-RSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-ECDSA-CHACHA20-POLY1305",
        "ECDHE-RSA-CHACHA20-POLY1305",
        "DHE-RSA-AES128-GCM-SHA256",
        "DHE-RSA-AES256-GCM-SHA384",
        "DHE-RSA-CHACHA20-POLY1305",
    )
)


def uvicorn_tls_kwargs(key_file: str, cert_file: str, chain_file: str = None) -> dict:
    """The ``uvicorn.run`` TLS arguments for this server."""
    kwargs = {
        "ssl_keyfile": key_file,
        "ssl_certfile": cert_file,
        "ssl_ciphers": SERVER_CIPHERS,
    }
    if chain_file:
        kwargs["ssl_ca_certs"] = chain_file
    return kwargs

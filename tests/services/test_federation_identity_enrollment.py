# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Security tests for strict out-of-band Ed25519 enrollment (Phase 12).

Two layers:

  * The crypto core in ``federation_identity_service`` — sign/verify, the
    canonical proof message, and that the proof is bound to the exact cert
    fingerprint, role, and key (so a swap, replay-across-role, or wrong key
    all fail).
  * The strict enrollment gates in the coordinator + site services — that
    enrollment is REFUSED without a registered identity key and a valid proof,
    and that the proof must match the presented cert.

These are the tests that guard the actual MITM defence; if any of the
"tampered ... still verifies" assertions ever flip, the gate is broken.
"""

# pylint: disable=redefined-outer-name

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence import models  # noqa: F401  # register all models
from backend.services import federation_coordinator_service as csvc
from backend.services import federation_identity_service as idsvc
from backend.services import federation_site_service as ssvc
from tests.federation_crypto import (
    make_identity_keypair,
    make_self_signed_cert,
    sign_enrollment_proof,
)


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with sessionmaker(bind=engine, expire_on_commit=False)() as s:
            yield s
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Crypto core
# ---------------------------------------------------------------------------


class TestProofCore:
    def test_sign_then_verify_roundtrip(self):
        priv, pub = make_identity_keypair()
        cert = make_self_signed_cert("peer")
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=cert)
        assert idsvc.verify_enrollment_proof(
            role="site",
            tls_cert_pem=cert,
            signature_b64=proof,
            peer_identity_public_pem=pub,
        )

    def test_proof_is_bound_to_the_cert(self):
        """A proof over cert A must NOT verify against cert B — this is the
        anti-cert-swap (MITM) guarantee."""
        priv, pub = make_identity_keypair()
        cert_a = make_self_signed_cert("a")
        cert_b = make_self_signed_cert("b")
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=cert_a)
        assert not idsvc.verify_enrollment_proof(
            role="site",
            tls_cert_pem=cert_b,
            signature_b64=proof,
            peer_identity_public_pem=pub,
        )

    def test_proof_is_bound_to_the_role(self):
        """A 'site' proof must not verify as a 'coordinator' proof."""
        priv, pub = make_identity_keypair()
        cert = make_self_signed_cert("peer")
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=cert)
        assert not idsvc.verify_enrollment_proof(
            role="coordinator",
            tls_cert_pem=cert,
            signature_b64=proof,
            peer_identity_public_pem=pub,
        )

    def test_wrong_key_does_not_verify(self):
        """A proof signed by one identity must not verify against another's
        public key (defeats a MITM substituting its own identity)."""
        priv, _pub = make_identity_keypair()
        _other_priv, other_pub = make_identity_keypair()
        cert = make_self_signed_cert("peer")
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=cert)
        assert not idsvc.verify_enrollment_proof(
            role="site",
            tls_cert_pem=cert,
            signature_b64=proof,
            peer_identity_public_pem=other_pub,
        )

    def test_tampered_signature_does_not_verify(self):
        priv, pub = make_identity_keypair()
        cert = make_self_signed_cert("peer")
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=cert)
        # Flip a character in the base64 signature.
        bad = ("A" if proof[0] != "A" else "B") + proof[1:]
        assert not idsvc.verify_enrollment_proof(
            role="site",
            tls_cert_pem=cert,
            signature_b64=bad,
            peer_identity_public_pem=pub,
        )

    @pytest.mark.parametrize(
        "sig,key,cert",
        [
            ("", "pub", "cert"),  # no signature
            ("sig", "", "cert"),  # no key
            ("sig", "pub", ""),  # no cert
        ],
    )
    def test_missing_inputs_fail_closed(self, sig, key, cert):
        priv, pub = make_identity_keypair()
        real_cert = make_self_signed_cert("peer")
        real_sig = sign_enrollment_proof(priv, role="site", tls_cert_pem=real_cert)
        args = {
            "role": "site",
            "tls_cert_pem": real_cert if cert else "",
            "signature_b64": real_sig if sig else "",
            "peer_identity_public_pem": pub if key else "",
        }
        assert idsvc.verify_enrollment_proof(**args) is False

    def test_non_cert_pem_fails_closed(self):
        priv, pub = make_identity_keypair()
        proof = sign_enrollment_proof(
            priv, role="site", tls_cert_pem=make_self_signed_cert("peer")
        )
        # A garbage "cert" can't be fingerprinted → verification returns False,
        # never raises.
        assert (
            idsvc.verify_enrollment_proof(
                role="site",
                tls_cert_pem="not-a-cert",
                signature_b64=proof,
                peer_identity_public_pem=pub,
            )
            is False
        )

    def test_bad_role_raises_in_message_builder(self):
        with pytest.raises(ValueError):
            idsvc.enrollment_proof_message(
                role="bogus", tls_cert_pem=make_self_signed_cert("x")
            )

    def test_fingerprint_is_stable_and_distinct(self):
        cert_a = make_self_signed_cert("a")
        cert_b = make_self_signed_cert("b")
        assert idsvc.tls_cert_fingerprint(cert_a) == idsvc.tls_cert_fingerprint(cert_a)
        assert idsvc.tls_cert_fingerprint(cert_a) != idsvc.tls_cert_fingerprint(cert_b)


# ---------------------------------------------------------------------------
# Coordinator-side strict gate (complete_enrollment verifies the SITE proof)
# ---------------------------------------------------------------------------


class TestCoordinatorEnrollmentGate:
    def _create(self, session, *, with_key=True):
        priv, pub = make_identity_keypair()
        cert = make_self_signed_cert("site")
        _site, token = ssvc.create_site(
            session,
            name="alpha",
            url="https://a.x",
            site_identity_public_key_pem=pub if with_key else None,
        )
        session.commit()
        return priv, cert, token

    def test_valid_proof_enrolls(self, session):
        priv, cert, token = self._create(session)
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=cert)
        site, bearer, _ = ssvc.complete_enrollment(
            session, plaintext_token=token, tls_cert_pem=cert, identity_proof_b64=proof
        )
        assert site.status == ssvc.STATUS_ENROLLED
        assert bearer

    def test_no_registered_key_refuses(self, session):
        _priv, cert, token = self._create(session, with_key=False)
        with pytest.raises(ssvc.IdentityProofError):
            ssvc.complete_enrollment(
                session,
                plaintext_token=token,
                tls_cert_pem=cert,
                identity_proof_b64="anything",
            )

    def test_missing_proof_refuses(self, session):
        _priv, cert, token = self._create(session)
        with pytest.raises(ssvc.IdentityProofError):
            ssvc.complete_enrollment(session, plaintext_token=token, tls_cert_pem=cert)

    def test_proof_over_different_cert_refuses(self, session):
        """The site proves a cert, then presents a DIFFERENT one (the MITM
        cert) — must be refused so the coordinator never pins it."""
        priv, _cert, token = self._create(session)
        signed_cert = make_self_signed_cert("real")
        presented_cert = make_self_signed_cert("mitm")
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=signed_cert)
        with pytest.raises(ssvc.IdentityProofError):
            ssvc.complete_enrollment(
                session,
                plaintext_token=token,
                tls_cert_pem=presented_cert,
                identity_proof_b64=proof,
            )

    def test_proof_from_wrong_identity_refuses(self, session):
        _priv, cert, token = self._create(session)
        attacker_priv, _attacker_pub = make_identity_keypair()
        proof = sign_enrollment_proof(attacker_priv, role="site", tls_cert_pem=cert)
        with pytest.raises(ssvc.IdentityProofError):
            ssvc.complete_enrollment(
                session,
                plaintext_token=token,
                tls_cert_pem=cert,
                identity_proof_b64=proof,
            )

    def test_create_site_rejects_malformed_identity_key(self, session):
        with pytest.raises(ValueError):
            ssvc.create_site(
                session,
                name="bad",
                url="https://b.x",
                site_identity_public_key_pem="-----BEGIN PUBLIC KEY-----\nnope\n",
            )


# ---------------------------------------------------------------------------
# Site-side strict gate (verify_coordinator_identity_proof before pinning)
# ---------------------------------------------------------------------------


class TestSiteCoordinatorGate:
    def _start(self, session, *, with_key=True):
        priv, pub = make_identity_keypair()
        cert = make_self_signed_cert("coord")
        csvc.start_enrollment(
            session,
            coordinator_url="https://c",
            coordinator_tls_cert_pem=cert,
            coordinator_identity_public_key_pem=pub if with_key else None,
        )
        session.commit()
        return priv, cert

    def test_valid_coordinator_proof_accepts(self, session):
        priv, cert = self._start(session)
        proof = sign_enrollment_proof(priv, role="coordinator", tls_cert_pem=cert)
        assert csvc.verify_coordinator_identity_proof(
            session, coordinator_tls_cert_pem=cert, identity_proof_b64=proof
        )

    def test_no_registered_key_rejects(self, session):
        _priv, cert = self._start(session, with_key=False)
        assert not csvc.verify_coordinator_identity_proof(
            session, coordinator_tls_cert_pem=cert, identity_proof_b64="x"
        )

    def test_missing_proof_rejects(self, session):
        _priv, cert = self._start(session)
        assert not csvc.verify_coordinator_identity_proof(
            session, coordinator_tls_cert_pem=cert, identity_proof_b64=None
        )

    def test_swapped_cert_rejects(self, session):
        priv, cert = self._start(session)
        proof = sign_enrollment_proof(priv, role="coordinator", tls_cert_pem=cert)
        mitm_cert = make_self_signed_cert("mitm")
        assert not csvc.verify_coordinator_identity_proof(
            session, coordinator_tls_cert_pem=mitm_cert, identity_proof_b64=proof
        )

    def test_wrong_identity_rejects(self, session):
        _priv, cert = self._start(session)
        attacker_priv, _ = make_identity_keypair()
        proof = sign_enrollment_proof(
            attacker_priv, role="coordinator", tls_cert_pem=cert
        )
        assert not csvc.verify_coordinator_identity_proof(
            session, coordinator_tls_cert_pem=cert, identity_proof_b64=proof
        )

    def test_no_coordinator_row_rejects(self, session):
        # Never started enrollment → no singleton row → fail closed.
        assert not csvc.verify_coordinator_identity_proof(
            session,
            coordinator_tls_cert_pem=make_self_signed_cert("c"),
            identity_proof_b64="x",
        )

    def test_start_enrollment_rejects_malformed_identity_key(self, session):
        with pytest.raises(ValueError):
            csvc.start_enrollment(
                session,
                coordinator_url="https://c",
                coordinator_tls_cert_pem=make_self_signed_cert("c"),
                coordinator_identity_public_key_pem="garbage",
            )

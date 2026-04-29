"""
Package compliance evaluator (Phase 8.3).

Single function, ``evaluate_host_against_profile``, takes a list of
"installed packages" (dicts with name + version + optional manager)
and a ``PackageProfile`` row plus its constraints, and returns
``(status, violations)`` where status is one of
``STATUS_COMPLIANT``/``STATUS_NON_COMPLIANT`` and violations is a
list of dicts the UI can render directly.

Version comparison uses ``packaging.version.Version`` for SemVer-style
strings; non-SemVer falls back to a lexicographic compare with a
warning in the violation reason (so non-SemVer doesn't silently let
a constraint pass).
"""

from typing import Any, Dict, Iterable, List, Tuple

from backend.persistence.models.package_compliance import (
    CONSTRAINT_BLOCKED,
    CONSTRAINT_REQUIRED,
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
)

try:
    from packaging.version import InvalidVersion, Version
except ImportError:  # pragma: no cover
    Version = None
    InvalidVersion = Exception


def _compare_versions(installed: str, op: str, target: str) -> Tuple[bool, str]:
    """Return (passes, reason).  ``reason`` is empty when passing or
    explanatory when not (UI will display this directly)."""
    if Version is None:
        # packaging not installed — fall back to lexicographic.
        return _lex_compare(installed, op, target), ""
    try:
        iv = Version(installed)
        tv = Version(target)
    except InvalidVersion:
        # Either side isn't SemVer; warn-but-evaluate via lex compare.
        ok = _lex_compare(installed, op, target)
        if ok:
            return True, ""
        return (
            False,
            f"non-SemVer version comparison ({installed} {op} {target})",
        )
    if op in ("=", "=="):
        return (iv == tv, "")
    if op == "!=":
        return (iv != tv, "")
    if op == ">":
        return (iv > tv, "")
    if op == ">=":
        return (iv >= tv, "")
    if op == "<":
        return (iv < tv, "")
    if op == "<=":
        return (iv <= tv, "")
    if op == "~=":
        # PEP 440 compatible-release.  packaging implements this directly.
        try:
            from packaging.specifiers import SpecifierSet  # local import

            return (iv in SpecifierSet(f"~={target}"), "")
        except Exception:  # pragma: no cover
            return (False, f"unsupported version operator: {op}")
    return (False, f"unknown version operator: {op}")


def _lex_compare(installed: str, op: str, target: str) -> bool:
    if op in ("=", "=="):
        return installed == target
    if op == "!=":
        return installed != target
    if op == ">":
        return installed > target
    if op == ">=":
        return installed >= target
    if op == "<":
        return installed < target
    if op == "<=":
        return installed <= target
    return False


def _packages_matching(
    constraint, installed: Iterable[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Return every entry in ``installed`` that matches the
    constraint's package_name (and package_manager if specified)."""
    out = []
    for pkg in installed:
        if pkg.get("name") != constraint.package_name:
            continue
        if constraint.package_manager and (
            pkg.get("manager") != constraint.package_manager
        ):
            continue
        out.append(pkg)
    return out


def evaluate_host_against_profile(
    installed_packages: Iterable[Dict[str, Any]], profile_constraints
) -> Tuple[str, List[Dict[str, Any]]]:
    """Evaluate one host's package list against one profile.

    Args:
        installed_packages: iterable of dicts with at least ``name`` and
            ``version`` keys; ``manager`` is optional.
        profile_constraints: iterable of PackageProfileConstraint rows.

    Returns:
        ``(status, violations)``.  ``status`` is COMPLIANT or
        NON_COMPLIANT; ``violations`` is a list of
        ``{constraint_id, package_name, reason}`` dicts.  An empty
        violations list with NON_COMPLIANT status is impossible —
        the function only returns NON_COMPLIANT when at least one
        violation is recorded.
    """
    installed = list(installed_packages)
    violations: List[Dict[str, Any]] = []

    for constraint in profile_constraints:
        matches = _packages_matching(constraint, installed)

        if constraint.constraint_type == CONSTRAINT_REQUIRED:
            if not matches:
                violations.append(
                    {
                        "constraint_id": str(constraint.id),
                        "package_name": constraint.package_name,
                        "constraint_type": CONSTRAINT_REQUIRED,
                        "reason": "package not installed",
                    }
                )
                continue
            if constraint.version_op and constraint.version:
                # At least one matching install must satisfy the version op.
                ok = False
                fail_reason = "no installed version satisfies the constraint"
                for pkg in matches:
                    iv = pkg.get("version", "")
                    passes, reason = _compare_versions(
                        iv, constraint.version_op, constraint.version
                    )
                    if passes:
                        ok = True
                        break
                    if reason:
                        fail_reason = reason
                if not ok:
                    violations.append(
                        {
                            "constraint_id": str(constraint.id),
                            "package_name": constraint.package_name,
                            "constraint_type": CONSTRAINT_REQUIRED,
                            "reason": fail_reason,
                        }
                    )

        elif constraint.constraint_type == CONSTRAINT_BLOCKED:
            if not matches:
                continue
            # If a version constraint is set, the BLOCKED rule fires
            # only when an installed version satisfies the op (i.e.,
            # "block versions less than 2.0").  If no version op is
            # set, ANY install of the package is a violation.
            if constraint.version_op and constraint.version:
                offending = []
                for pkg in matches:
                    iv = pkg.get("version", "")
                    passes, _ = _compare_versions(
                        iv, constraint.version_op, constraint.version
                    )
                    if passes:
                        offending.append(iv)
                if offending:
                    violations.append(
                        {
                            "constraint_id": str(constraint.id),
                            "package_name": constraint.package_name,
                            "constraint_type": CONSTRAINT_BLOCKED,
                            "reason": (
                                f"installed version(s) match blocked constraint: "
                                f"{', '.join(offending)}"
                            ),
                        }
                    )
            else:
                violations.append(
                    {
                        "constraint_id": str(constraint.id),
                        "package_name": constraint.package_name,
                        "constraint_type": CONSTRAINT_BLOCKED,
                        "reason": "package is installed but blocked",
                    }
                )

    status = STATUS_COMPLIANT if not violations else STATUS_NON_COMPLIANT
    return status, violations

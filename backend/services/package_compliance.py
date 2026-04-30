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


def _violation(constraint, ctype: str, reason: str) -> Dict[str, Any]:
    """Shape the violation dict the UI renders directly."""
    return {
        "constraint_id": str(constraint.id),
        "package_name": constraint.package_name,
        "constraint_type": ctype,
        "reason": reason,
    }


def _check_version_satisfied(
    matches: Iterable[Dict[str, Any]], op: str, target: str
) -> Tuple[bool, str]:
    """For REQUIRED + version-op: returns (any_match_passes, fail_reason).
    Used to keep the per-constraint dispatcher flat."""
    fail_reason = "no installed version satisfies the constraint"
    for pkg in matches:
        passes, reason = _compare_versions(pkg.get("version", ""), op, target)
        if passes:
            return True, ""
        if reason:
            fail_reason = reason
    return False, fail_reason


def _eval_required(constraint, matches: List[Dict[str, Any]]):
    """Evaluate a single REQUIRED constraint;  returns a violation dict
    or None when the host satisfies the rule."""
    if not matches:
        return _violation(constraint, CONSTRAINT_REQUIRED, "package not installed")
    if constraint.version_op and constraint.version:
        ok, fail_reason = _check_version_satisfied(
            matches, constraint.version_op, constraint.version
        )
        if not ok:
            return _violation(constraint, CONSTRAINT_REQUIRED, fail_reason)
    return None


def _eval_blocked(constraint, matches: List[Dict[str, Any]]):
    """Evaluate a single BLOCKED constraint.

    With a version op set the rule fires only when an installed version
    satisfies the op (i.e. "block < 2.0").  Without a version op, any
    install of the package is a violation."""
    if not matches:
        return None
    if not (constraint.version_op and constraint.version):
        return _violation(
            constraint, CONSTRAINT_BLOCKED, "package is installed but blocked"
        )
    offending: List[str] = []
    for pkg in matches:
        iv = pkg.get("version", "")
        passes, _ = _compare_versions(iv, constraint.version_op, constraint.version)
        if passes:
            offending.append(iv)
    if not offending:
        return None
    return _violation(
        constraint,
        CONSTRAINT_BLOCKED,
        f"installed version(s) match blocked constraint: {', '.join(offending)}",
    )


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
            v = _eval_required(constraint, matches)
        elif constraint.constraint_type == CONSTRAINT_BLOCKED:
            v = _eval_blocked(constraint, matches)
        else:
            v = None
        if v is not None:
            violations.append(v)

    status = STATUS_COMPLIANT if not violations else STATUS_NON_COMPLIANT
    return status, violations

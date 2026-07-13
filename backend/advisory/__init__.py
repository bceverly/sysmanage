"""Advisory / errata management (Phase 14.1).

OSS-side scaffolding for the "patch by advisory" abstraction: the advisory source
registry + shared-partition schema (see ``backend/persistence/models/advisory.py``).
The ingestion + per-host applicability *logic* lives in the Pro+ ``advisory_engine``
(moat model); this package holds only what is OSS.
"""

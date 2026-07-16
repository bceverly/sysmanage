# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""OS lifecycle / release-upgrade orchestration (Phase 14.3).

OSS-side scaffolding: the lifecycle source registry + shared/tenant schema (see
``backend/persistence/models/os_lifecycle.py``).  The lifecycle ingestion, the
per-host "approaching EOL" computation, and the release-upgrade orchestration
*logic* live in the Pro+ ``lifecycle_engine`` (moat model); this package holds
only what is OSS.
"""

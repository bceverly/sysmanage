// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Operator-visible policy types.  Mirrored from
// federation_policy_service's docstring -- the engine accepts any
// string but the UI offers these common shapes as a select.  Free-
// form input remains available via the "Other..." sentinel.
export const KNOWN_POLICY_TYPES = [
  "update_profile",
  "firewall_role",
  "compliance_baseline",
  "backup_tag_policy",
];

// A starting definition for the types whose shape is not obvious.  A
// backup tag policy (27.3) names its target by name or location; each site
// resolves it to one of its own targets, else uses its default.
export const DEFINITION_TEMPLATES: Record<string, string> = {
  backup_tag_policy: JSON.stringify(
    {
      name: "Web servers",
      tag: "web",
      priority: 50,
      enabled: true,
      settings: { interval_hours: 24, window_start_hour: 2, keep_last: 30 },
      target: { name: "Offsite" },
    },
    null,
    2,
  ),
};

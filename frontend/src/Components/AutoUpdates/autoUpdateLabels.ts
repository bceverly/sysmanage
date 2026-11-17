// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The words for automatic-update codes (ROADMAP 26.1).  The server and the
// engine send codes; the UI owns the wording.

import type { TFunction } from 'i18next';

export function runStatusLabel(t: TFunction, status: string): string {
  const labels: Record<string, string> = {
    queued: t('autoUpdates.status.queued', 'Running'),
    succeeded: t('autoUpdates.status.succeeded', 'Succeeded'),
    partial: t('autoUpdates.status.partial', 'Partly failed'),
    failed: t('autoUpdates.status.failed', 'Failed'),
    nothing_to_do: t('autoUpdates.status.nothingToDo', 'Nothing to do'),
    skipped: t('autoUpdates.status.skipped', 'Skipped'),
    timed_out: t('autoUpdates.status.timedOut', 'No result'),
    waiting: t('autoUpdates.status.waiting', 'Waiting for its window'),
  };
  return labels[status] ?? status;
}

export function runStatusColor(
  status: string,
): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (status === 'succeeded') return 'success';
  if (status === 'partial') return 'warning';
  if (status === 'failed' || status === 'timed_out') return 'error';
  if (status === 'queued' || status === 'waiting') return 'info';
  return 'default';
}

export function skipReasonLabel(t: TFunction, reason: string | null): string {
  if (!reason) return '';
  const labels: Record<string, string> = {
    inactive: t('autoUpdates.skip.inactive', 'the host is inactive'),
    not_approved: t('autoUpdates.skip.notApproved', 'the host is not approved'),
    opted_out: t('autoUpdates.skip.optedOut', 'the host never updates automatically'),
    image_mode: t('autoUpdates.skip.imageMode', 'an image-mode host updates its image instead'),
    package_manager_needs_repair: t(
      'autoUpdates.skip.needsRepair',
      'the package manager needs repair',
    ),
    previous_run_pending: t('autoUpdates.skip.pending', 'its previous run has not finished'),
    previous_run_failed: t(
      'autoUpdates.skip.failedRecently',
      'its previous run failed; it waits until someone acknowledges it or the retry hours pass',
    ),
    no_recent_backup: t('autoUpdates.skip.noBackup', 'it has no recent good backup'),
    agent_cannot_apply: t('autoUpdates.skip.agentCannotApply', 'its agent cannot apply updates; update the agent'),
    no_window_long_enough: t(
      'autoUpdates.skip.noWindow',
      'none of its maintenance windows in the next week is long enough for the run',
    ),
    policy_changed: t(
      'autoUpdates.skip.policyChanged',
      'its policy was turned off or deleted while the run waited',
    ),
  };
  return labels[reason] ?? reason;
}

export function packageReasonLabel(t: TFunction, reason: string): string {
  const labels: Record<string, string> = {
    held: t('autoUpdates.pkg.held', 'held on the host'),
    excluded: t('autoUpdates.pkg.excluded', 'excluded by the policy'),
    not_security: t('autoUpdates.pkg.notSecurity', 'not a security update'),
    package_manager_not_allowed: t(
      'autoUpdates.pkg.manager',
      'package manager not in the policy',
    ),
    os_upgrade: t('autoUpdates.pkg.osUpgrade', 'an OS upgrade is never automatic'),
    firmware: t('autoUpdates.pkg.firmware', 'firmware only when the policy names fwupd'),
    sysmanage_agent: t('autoUpdates.pkg.agent', 'the agent updates through Update Agent'),
    already_updating: t('autoUpdates.pkg.busy', 'already being updated'),
    waiting_period: t('autoUpdates.pkg.waiting', 'waiting its days'),
  };
  return labels[reason] ?? reason;
}

export function rebootLabel(t: TFunction, status: string): string {
  const labels: Record<string, string> = {
    none: '',
    queued: t('autoUpdates.reboot.queued', 'Rebooting'),
    back: t('autoUpdates.reboot.back', 'Rebooted and back'),
    not_back: t('autoUpdates.reboot.notBack', 'Did not come back from its reboot'),
    next_window: t('autoUpdates.reboot.nextWindow', 'Reboot required: waits for its next window'),
    not_needed: t('autoUpdates.reboot.notNeeded', 'Reboot no longer needed'),
  };
  return labels[status] ?? status;
}

export function policyRuleLabel(t: TFunction, rule: string): string {
  const labels: Record<string, string> = {
    only: t('autoUpdates.rule.only', 'the only policy that covers this host'),
    more_specific: t('autoUpdates.rule.moreSpecific', 'the most specific policy that covers it'),
    more_conservative: t(
      'autoUpdates.rule.moreConservative',
      'the more conservative of equally specific policies',
    ),
  };
  return labels[rule] ?? rule;
}

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Words and colors for time synchronization (Phase 23.3).  "Not measured" is
// never shown as in sync: unmeasured, stale and server-clock-off each say
// what they are.

import type { TFunction } from 'i18next';
import type { BoundsSource, ClockStatus, ResyncStatus, ServerClock } from '../../Services/timeSync';

type ChipColor = 'success' | 'warning' | 'error' | 'default' | 'info';

export const statusLabel = (t: TFunction, status: ClockStatus): string => {
    const labels: Record<ClockStatus, string> = {
        ok: t('timeSync.status.ok', 'In bounds'),
        warning: t('timeSync.status.warning', 'Warning'),
        critical: t('timeSync.status.critical', 'Critical'),
        unmeasured: t('timeSync.status.unmeasured', 'Not measured'),
        stale: t('timeSync.status.stale', 'No recent measurement'),
        uncertain: t('timeSync.status.uncertain', 'Uncertain'),
        server_clock_off: t('timeSync.status.serverClockOff', 'Server clock off'),
    };
    return labels[status] ?? status;
};

export const statusColor = (status: ClockStatus): ChipColor => {
    switch (status) {
        case 'ok':
            return 'success';
        case 'warning':
            return 'warning';
        case 'critical':
            return 'error';
        case 'server_clock_off':
            return 'info';
        default:
            return 'default';
    }
};

/** Why a status was given, in a sentence, for a tooltip or the host card. */
export const statusHelp = (t: TFunction, status: ClockStatus): string => {
    const help: Record<ClockStatus, string> = {
        ok: t('timeSync.statusHelp.ok', 'The measured offset is below the warning bound.'),
        warning: t('timeSync.statusHelp.warning', 'The measured offset is at or beyond the warning bound.'),
        critical: t('timeSync.statusHelp.critical', 'The measured offset is at or beyond the critical bound.'),
        unmeasured: t('timeSync.statusHelp.unmeasured', 'The server has not measured this clock yet. The agent may be too old, or has not connected.'),
        stale: t('timeSync.statusHelp.stale', 'The last measurement is more than 30 minutes old. The host is probably not connected.'),
        uncertain: t('timeSync.statusHelp.uncertain', 'The last exchange took too long to measure the offset to within the warning bound, so the clock is not judged until a quicker exchange.'),
        server_clock_off: t('timeSync.statusHelp.serverClockOff', "The server's own clock is off its reference, so host clocks are not judged until it is corrected."),
    };
    return help[status] ?? '';
};

/** A signed offset in the unit that suits its size: +0.4 ms, -224 ms,
 *  +1.33 s, +12 min, +2.0 h. */
export const formatOffset = (t: TFunction, ms: number | null | undefined): string => {
    if (ms === null || ms === undefined) {
        return '-';
    }
    let sign = '';
    if (ms > 0) {
        sign = '+';
    } else if (ms < 0) {
        sign = '-';
    }
    const abs = Math.abs(ms);
    if (abs < 1000) {
        const value = `${sign}${abs.toFixed(abs < 10 ? 1 : 0)}`;
        return t('timeSync.unit.ms', '{{value}} ms', { value });
    }
    if (abs < 60_000) {
        return t('timeSync.unit.s', '{{value}} s', { value: `${sign}${(abs / 1000).toFixed(2)}` });
    }
    if (abs < 3_600_000) {
        return t('timeSync.unit.min', '{{value}} min', { value: `${sign}${Math.round(abs / 60_000)}` });
    }
    return t('timeSync.unit.h', '{{value}} h', { value: `${sign}${(abs / 3_600_000).toFixed(1)}` });
};

/** "Ahead" or "behind", so a sign never has to be decoded. */
export const offsetDirection = (t: TFunction, ms: number | null | undefined): string => {
    if (!ms) {
        return '';
    }
    return ms > 0
        ? t('timeSync.direction.ahead', 'ahead of the server')
        : t('timeSync.direction.behind', 'behind the server');
};

export const sourceLabel = (t: TFunction, source: BoundsSource): string => {
    const labels: Record<BoundsSource, string> = {
        default: t('timeSync.boundsSource.default', 'Built-in default'),
        server: t('timeSync.boundsSource.server', 'Server-wide'),
        tenant: t('timeSync.boundsSource.tenant', 'Tenant'),
        site: t('timeSync.boundsSource.site', 'Site'),
        tag: t('timeSync.boundsSource.tag', 'Tag'),
    };
    return labels[source] ?? source;
};

/** The server's own clock, in a sentence. */
export const serverClockText = (t: TFunction, server: ServerClock): string => {
    const offset = formatOffset(t, server.offset_ms);
    switch (server.reason) {
        case null:
            return t('timeSync.server.verified', "The server's clock is {{offset}} from {{reference}}. Host offsets are measured against it.", {
                offset,
                reference: server.reference,
            });
        case 'server_off':
            return t('timeSync.server.off', "The server's own clock is {{offset}} from {{reference}}. Host clocks are not judged until the server's clock is corrected.", {
                offset,
                reference: server.reference,
            });
        case 'unreachable':
            return t('timeSync.server.unreachable', "The server could not reach its time reference {{reference}}. Host offsets are measured against the server's clock, which could not be checked.", {
                reference: server.reference,
            });
        case 'no_reference':
            return t('timeSync.server.noReference', "No time reference is configured, so the server's own clock is not checked. Host offsets are measured against it.");
        default:
            return server.reason;
    }
};

export const serverClockSeverity = (server: ServerClock): 'success' | 'warning' | 'error' => {
    if (server.reason === 'server_off') {
        return 'error';
    }
    return server.verified ? 'success' : 'warning';
};

/** A refused bound, from its code. */
export const boundsErrorText = (t: TFunction, code: string | null): string => {
    switch (code) {
        case 'warning_not_below_critical':
            return t('timeSync.boundsError.order', 'The warning bound must be smaller than the critical bound.');
        case 'out_of_range':
            return t('timeSync.boundsError.range', 'Each bound must be between 1 ms and 24 hours.');
        case 'not_a_number':
            return t('timeSync.boundsError.number', 'Each bound must be a number.');
        case 'tag_not_found':
            return t('timeSync.boundsError.tag', 'That tag no longer exists.');
        case 'bad_scope':
            return t('timeSync.boundsError.scope', 'Choose a tenant, site or tag.');
        case 'not_saved':
            return t('timeSync.boundsError.notSaved', 'The server could not save the bounds.');
        default:
            return t('timeSync.boundsError.unknown', 'The bounds could not be saved.');
    }
};

/** The host's own time service, by name. */
export const serviceName = (t: TFunction, service: string | null | undefined): string => {
    switch (service) {
        case null:
        case undefined:
            return t('timeSync.service.unknown', 'Not reported');
        case 'none':
            return t('timeSync.service.none', 'No time service');
        case 'chrony':
            return 'chrony';
        case 'ntpd':
            return 'ntpd';
        case 'timesyncd':
            return 'systemd-timesyncd';
        case 'openntpd':
            return 'OpenNTPD';
        case 'w32time':
            return 'Windows Time';
        case 'timed':
            return 'macOS timed';
        default:
            return service;
    }
};

// --- spot resync (Phase 23.3 S5) -------------------------------------------

export const resyncStatusLabel = (t: TFunction, status: ResyncStatus): string => {
    const labels: Record<ResyncStatus, string> = {
        queued: t('timeSync.resync.status.queued', 'Waiting'),
        sent: t('timeSync.resync.status.sent', 'In progress'),
        succeeded: t('timeSync.resync.status.succeeded', 'Resynchronized'),
        failed: t('timeSync.resync.status.failed', 'Failed'),
        unsupported: t('timeSync.resync.status.unsupported', 'Not possible'),
        timed_out: t('timeSync.resync.status.timedOut', 'No answer'),
    };
    return labels[status] ?? status;
};

export const resyncStatusColor = (status: ResyncStatus): ChipColor => {
    switch (status) {
        case 'succeeded':
            return 'success';
        case 'failed':
        case 'timed_out':
            return 'error';
        case 'unsupported':
            return 'warning';
        default:
            return 'info';
    }
};

/** Why a resync did not happen, from its code. */
export const resyncErrorText = (t: TFunction, code: string | null): string => {
    switch (code) {
        case null:
            return '';
        case 'not_privileged':
            return t('timeSync.resync.error.notPrivileged', 'The agent does not run with administrator rights, which setting the clock requires.');
        case 'agent_too_old':
            return t('timeSync.resync.error.agentTooOld', 'This agent is too old to resynchronize its clock. Update the agent.');
        case 'no_tool':
            return t('timeSync.resync.error.noTool', 'The host has no time service or time tool to resynchronize with.');
        case 'command_failed':
            return t('timeSync.resync.error.commandFailed', "The host's time service refused the resynchronization.");
        case 'bad_server':
            return t('timeSync.resync.error.badServer', 'No usable time server was available.');
        case 'no_result':
            return t('timeSync.resync.error.noResult', 'The host did not answer within 10 minutes. It may be offline.');
        case 'host_gone':
            return t('timeSync.resync.error.hostGone', 'The host was removed.');
        case 'dispatch_failed':
            return t('timeSync.resync.error.dispatchFailed', 'The server could not send the request to the host.');
        default:
            return t('timeSync.resync.error.agentError', 'The agent reported an error.');
    }
};

// --- fleet NTP policy (Phase 23.3 S5b) --------------------------------------

/** One difference between a host and its NTP policy, in words. */
export const policyFindingText = (t: TFunction, code: string): string => {
    switch (code) {
        case 'servers_differ':
            return t('timeSync.policy.finding.serversDiffer', 'Uses other NTP servers than the policy');
        case 'not_enabled':
            return t('timeSync.policy.finding.notEnabled', 'Time service not enabled at boot');
        case 'not_running':
            return t('timeSync.policy.finding.notRunning', 'Time service not running');
        case 'no_time_service':
            return t('timeSync.policy.finding.noService', 'No time service to configure');
        case 'not_reported':
        case 'servers_not_reported':
            return t('timeSync.policy.finding.notReported', 'The agent has not reported its time configuration');
        case 'policy_conflict':
            return t('timeSync.policy.finding.conflict', 'Two tag policies with different servers apply');
        default:
            return code;
    }
};

/** A refused policy, from its code. */
export const policyErrorText = (t: TFunction, code: string | null): string => {
    switch (code) {
        case 'no_servers':
            return t('timeSync.policy.error.noServers', 'Enter at least one NTP server.');
        case 'too_many_servers':
            return t('timeSync.policy.error.tooMany', 'Enter at most 8 NTP servers.');
        case 'bad_server':
            return t('timeSync.policy.error.badServer', 'Each server must be a host name or an IP address.');
        case 'duplicate_server':
            return t('timeSync.policy.error.duplicate', 'A server is listed twice.');
        case 'bad_scope':
            return t('timeSync.policy.error.scope', 'Choose the fleet, a site or a tag.');
        case 'tag_not_found':
            return t('timeSync.boundsError.tag', 'That tag no longer exists.');
        default:
            return t('timeSync.policy.error.unknown', 'The policy could not be saved.');
    }
};

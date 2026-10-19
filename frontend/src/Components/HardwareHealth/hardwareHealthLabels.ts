// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Words and colors for hardware health (Phase 23.1).  The agent sends reasons
// as codes with parameters; this is where they become sentences, in the
// reader's language.  "Not measured" is never shown as healthy.

import type { TFunction } from 'i18next';
import type {
    ComponentKind,
    HardwareEvent,
    HardwareSource,
    HardwareStatus,
    Reason,
} from '../../Services/hardwareHealth';

type ChipColor = 'success' | 'warning' | 'error' | 'default' | 'info';

export const statusLabel = (t: TFunction, status: HardwareStatus | 'gone'): string => {
    const labels: Record<string, string> = {
        ok: t('hardwareHealth.status.ok', 'Healthy'),
        warning: t('hardwareHealth.status.warning', 'Warning'),
        failed: t('hardwareHealth.status.failed', 'Failed'),
        unknown: t('hardwareHealth.status.unknown', 'Not judged'),
        unmeasured: t('hardwareHealth.status.unmeasured', 'Not reported'),
        stale: t('hardwareHealth.status.stale', 'No recent report'),
        none: t('hardwareHealth.status.none', 'No physical hardware'),
        gone: t('hardwareHealth.status.gone', 'No longer reported'),
    };
    return labels[status] ?? status;
};

export const statusColor = (status: HardwareStatus | 'gone'): ChipColor => {
    const colors: Record<string, ChipColor> = {
        ok: 'success',
        warning: 'warning',
        failed: 'error',
        gone: 'error',
        stale: 'info',
        // none: 'default' -- neutral; a VM with nothing to watch is not a problem
    };
    return colors[status] ?? 'default';
};

export const statusHelp = (t: TFunction, status: HardwareStatus): string => {
    const help: Record<HardwareStatus, string> = {
        ok: t('hardwareHealth.statusHelp.ok', 'Every component the host reported is healthy.'),
        warning: t('hardwareHealth.statusHelp.warning', 'At least one component needs attention.'),
        failed: t('hardwareHealth.statusHelp.failed', 'At least one component has failed.'),
        unknown: t('hardwareHealth.statusHelp.unknown', 'The host reported its hardware, but nothing could judge at least one component.'),
        unmeasured: t('hardwareHealth.statusHelp.unmeasured', 'The host has never reported its hardware. Its agent may be too old, or it has not connected.'),
        stale: t('hardwareHealth.statusHelp.stale', 'The last report is more than an hour old. The host is probably not connected.'),
        none: t('hardwareHealth.statusHelp.none', 'Nothing to monitor: no drives, sensors or ECC memory were found (typical for a virtual machine).'),
    };
    return help[status] ?? '';
};

export const kindLabel = (t: TFunction, kind: ComponentKind | 'system'): string => {
    const labels: Record<ComponentKind | 'system', string> = {
        drive: t('hardwareHealth.kind.drive', 'Drive'),
        array: t('hardwareHealth.kind.array', 'RAID array'),
        pool: t('hardwareHealth.kind.pool', 'Storage pool'),
        sensor: t('hardwareHealth.kind.sensor', 'Sensor'),
        memory: t('hardwareHealth.kind.memory', 'Memory'),
        system: t('hardwareHealth.kind.system', 'Operating system'),
    };
    return labels[kind] ?? kind;
};

// Every reason the agent can send, worded.  Literal t() calls, so the i18n
// tooling sees each key; an unknown code (a newer agent) shows as itself.
type Params = Record<string, unknown>;
const reasonWords = (t: TFunction, p: Params): Record<string, string> => ({
    spare_below_threshold: t('hardwareHealth.reason.spareBelowThreshold', 'Spare capacity is below its threshold', p),
    temperature_threshold: t('hardwareHealth.reason.temperatureThreshold', 'Temperature is beyond a threshold', p),
    reliability_degraded: t('hardwareHealth.reason.reliabilityDegraded', 'Reliability is degraded by media or internal errors', p),
    read_only: t('hardwareHealth.reason.readOnly', 'The drive has made itself read-only', p),
    volatile_backup_failed: t('hardwareHealth.reason.volatileBackupFailed', 'The volatile memory backup has failed', p),
    pmr_read_only: t('hardwareHealth.reason.pmrReadOnly', 'The persistent memory region is read-only', p),
    endurance_used: t('hardwareHealth.reason.enduranceUsed', '{{percent}}% of rated endurance used', p),
    media_errors: t('hardwareHealth.reason.mediaErrors', 'Media and data integrity errors: {{n}}', p),
    smart_not_read: t('hardwareHealth.reason.smartNotRead', 'The health log could not be read', p),
    smart_failed: t('hardwareHealth.reason.smartFailed', 'The SMART overall health check failed', p),
    smart_status: t('hardwareHealth.reason.smartStatus', 'SMART status: {{status}}', p),
    reallocated_sectors: t('hardwareHealth.reason.reallocatedSectors', 'Reallocated sectors: {{n}}', p),
    pending_sectors: t('hardwareHealth.reason.pendingSectors', 'Sectors pending reallocation: {{n}}', p),
    offline_uncorrectable: t('hardwareHealth.reason.offlineUncorrectable', 'Uncorrectable sectors: {{n}}', p),
    read_errors: t('hardwareHealth.reason.readErrors', 'Read errors: {{n}}', p),
    write_errors: t('hardwareHealth.reason.writeErrors', 'Write errors: {{n}}', p),
    smartctl_absent: t('hardwareHealth.reason.smartctlAbsent', 'smartctl is not installed, so SMART was not read', p),
    smartctl_failed: t('hardwareHealth.reason.smartctlFailed', 'smartctl failed (exit code {{rc}})', p),
    diskutil_failed: t('hardwareHealth.reason.diskutilFailed', 'diskutil could not describe the disk', p),
    health_status: t('hardwareHealth.reason.healthStatus', 'Health: {{status}}', p),
    operational_status: t('hardwareHealth.reason.operationalStatus', 'Operational status: {{status}}', p),
    pool_health: t('hardwareHealth.reason.poolHealth', 'Pool state: {{health}}', p),
    device_not_online: t('hardwareHealth.reason.deviceNotOnline', '{{device}} is {{state}}', p),
    device_errors: t('hardwareHealth.reason.deviceErrors', 'Device errors: {{read}} read, {{write}} write, {{cksum}} checksum', p),
    data_errors: t('hardwareHealth.reason.dataErrors', 'Data errors: {{detail}}', p),
    array_inactive: t('hardwareHealth.reason.arrayInactive', 'The array is not active ({{activity}})', p),
    array_degraded: t('hardwareHealth.reason.arrayDegraded', 'Degraded: {{active}} of {{total}} devices active', p),
    failed_members: t('hardwareHealth.reason.failedMembers', 'Failed members: {{members}}', p),
    rebuilding: t('hardwareHealth.reason.rebuilding', 'Rebuilding, {{percent}}% done', p),
    array_state: t('hardwareHealth.reason.arrayState', 'Array state: {{state}}', p),
    member_state: t('hardwareHealth.reason.memberState', 'Member: {{member}}', p),
    memory_counts_unreadable: t('hardwareHealth.reason.memoryCountsUnreadable', 'Memory error counts could not be read', p),
    memory_uncorrected: t('hardwareHealth.reason.memoryUncorrected', 'Uncorrected memory errors: {{n}}', p),
    memory_corrected: t('hardwareHealth.reason.memoryCorrected', 'Corrected memory errors: {{n}}', p),
    temperature_high: t('hardwareHealth.reason.temperatureHigh', '{{value}} C, at or above its limit of {{limit}} C', p),
    temperature_critical: t('hardwareHealth.reason.temperatureCritical', '{{value}} C, at or above its critical limit of {{limit}} C', p),
    sensor_status: t('hardwareHealth.reason.sensorStatus', '{{sensor}}: {{value}} ({{status}})', p),
    thermal_warning: t('hardwareHealth.reason.thermalWarning', 'Thermal warning level {{level}}', p),
    cpu_speed_limited: t('hardwareHealth.reason.cpuSpeedLimited', 'The CPU is held to {{percent}}% of its speed', p),
    thermal_unreported: t('hardwareHealth.reason.thermalUnreported', 'The thermal state was not reported', p),
    btrfs_device_errors: t('hardwareHealth.reason.btrfsDeviceErrors', '{{device}}: errors since the counters were last reset: {{write}} write, {{read}} read, {{flush}} flush, {{corruption}} corruption, {{generation}} generation', p),
    machine_checks: t('hardwareHealth.reason.machineChecks', 'Corrected hardware errors (machine checks) in the last 24 hours: {{n}}', p),
    machine_checks_fatal: t('hardwareHealth.reason.machineChecksFatal', 'Uncorrected hardware errors (machine checks) in the last 24 hours: {{n}}', p),
    controller_status: t('hardwareHealth.reason.controllerStatus', 'RAID controller status: {{status}}', p),
    cache_battery: t('hardwareHealth.reason.cacheBattery', 'Cache battery or capacitor status: {{status}}', p),
    sel_events: t('hardwareHealth.reason.selEvents', 'Hardware problems in the BMC event log in the last 24 hours: {{n}}. Most recent: {{last}}', p),
    os_storage_event: t('hardwareHealth.reason.osStorageEvent', 'Storage error reported by the operating system: {{text}}', p),
    os_thermal_event: t('hardwareHealth.reason.osThermalEvent', 'Temperature problem reported by the operating system: {{text}}', p),
    os_memory_event: t('hardwareHealth.reason.osMemoryEvent', 'Hardware error reported by the operating system: {{text}}', p),
    os_power_event: t('hardwareHealth.reason.osPowerEvent', 'Unexpected loss of power reported by the operating system: {{text}}', p),
});

const param = (value: unknown): string => {
    if (Array.isArray(value)) {
        return value.map(param).join(', ');
    }
    if (value === null || value === undefined) {
        return '-';
    }
    if (typeof value === 'object') {
        return JSON.stringify(value);
    }
    return String(value as string | number | boolean | bigint | symbol);
};

/** A reason as a sentence; an unknown code (a newer agent) shows as itself. */
export const reasonText = (t: TFunction, reason: Reason): string => {
    // ``count`` would make i18next look for plural keys: pass it as ``n``.
    const params = Object.fromEntries(
        Object.entries(reason)
            .filter(([key]) => key !== 'code')
            .map(([key, value]) => [key === 'count' ? 'n' : key, param(value)]),
    );
    const words = reasonWords(t, { ...params, interpolation: { escapeValue: false } });
    return Object.hasOwn(words, reason.code) ? words[reason.code] : reason.code;
};

export const reasonsText = (t: TFunction, reasons: Reason[]): string =>
    reasons.map(r => reasonText(t, r)).join('; ');

export const sourceStatusLabel = (t: TFunction, source: HardwareSource): string => {
    const labels: Record<HardwareSource['status'], string> = {
        ran: t('hardwareHealth.source.ran', 'read'),
        absent: t('hardwareHealth.source.absent', 'not present'),
        failed: t('hardwareHealth.source.failed', 'failed'),
    };
    return labels[source.status] ?? source.status;
};

/** "Healthy -> Warning", or "New: Warning" for a first sighting. */
export const transitionText = (t: TFunction, event: HardwareEvent): string => {
    const to = statusLabel(t, event.to_state);
    if (!event.from_state) {
        return t('hardwareHealth.event.new', 'New: {{to}}', { to });
    }
    return t('hardwareHealth.event.changed', '{{from}} -> {{to}}', {
        from: statusLabel(t, event.from_state),
        to,
        interpolation: { escapeValue: false },
    });
};

/** The readings worth a glance, in a short line: temperature, wear, hours. */
export const metricsText = (t: TFunction, metrics: Record<string, unknown>): string => {
    const parts: string[] = [];
    if (typeof metrics.temperature_c === 'number') {
        parts.push(t('hardwareHealth.metric.temperature', '{{value}} C', { value: metrics.temperature_c }));
    }
    if (metrics.high_source === 'host' && typeof metrics.high_c === 'number') {
        parts.push(t('hardwareHealth.metric.hostLimit', 'warns at {{limit}} C (host limit)', { limit: metrics.high_c }));
    }
    if (typeof metrics.percent_used === 'number') {
        parts.push(t('hardwareHealth.metric.wear', '{{value}}% worn', { value: metrics.percent_used }));
    }
    if (typeof metrics.power_on_hours === 'number') {
        parts.push(t('hardwareHealth.metric.hours', 'Power-on hours: {{value}}', { value: metrics.power_on_hours }));
    }
    return parts.join(', ');
};

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Hosts whose disk is nearly full (2026-11-20).  Production: a host's root
 * sat at 96-99 % for days with nothing said, until an update ran out of room
 * part-way and left its package manager half-configured.  Shown on the
 * host's page, the Updates page and the dashboard; renders nothing while
 * every disk has room.
 */

import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Link as RouterLink } from 'react-router';

import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Link from '@mui/material/Link';

import { doGetHostsSummary, SysManageHost } from '../Services/hosts';
import { formatBytes } from './Backups/backupLabels';

const SHOWN = 5;
// At this much used a full disk is an emergency, not a warning.
const CRITICAL_PERCENT = 97;

export const diskLine = (t: TFunction, host: SysManageHost): string => {
    const percent = Math.round(host.disk_used_percent ?? 0);
    if (host.disk_fullest_mount && host.disk_available_bytes != null) {
        return t('diskSpace.mountLine', '{{mount}} is {{percent}}% full ({{free}} free)', {
            mount: host.disk_fullest_mount,
            percent,
            free: formatBytes(host.disk_available_bytes),
        });
    }
    return t('diskSpace.percentLine', 'Its fullest disk is {{percent}}% full', { percent });
};

const DiskSpaceNotice: React.FC<{ host?: SysManageHost | null }> = ({ host }) => {
    const { t } = useTranslation();
    const [hosts, setHosts] = useState<SysManageHost[]>([]);
    const [total, setTotal] = useState(0);

    useEffect(() => {
        if (host !== undefined) {
            const shown = host?.disk_nearly_full ? [host] : [];
            setHosts(shown);
            setTotal(shown.length);
            return;
        }
        let gone = false;
        doGetHostsSummary()
            .then((summary) => {
                if (gone) return;
                setHosts(summary.disk_hosts ?? []);
                setTotal(summary.disk_nearly_full ?? 0);
            })
            .catch(() => { if (!gone) { setHosts([]); setTotal(0); } });
        return () => { gone = true; };
    }, [host]);

    if (hosts.length === 0) return null;
    const critical = hosts.some((h) => (h.disk_used_percent ?? 0) >= CRITICAL_PERCENT);
    return (
        <Alert severity={critical ? 'error' : 'warning'} sx={{ mb: 2 }} data-testid="disk-space-notice">
            <AlertTitle>{t('diskSpace.title', 'Disk nearly full')}</AlertTitle>
            {host ? (
                <Box>
                    {diskLine(t, hosts[0])}.{' '}
                    {t('diskSpace.why', 'Free some space or grow the disk before updating: an update that runs out of room stops part-way.')}
                </Box>
            ) : (
                <>
                    <Box sx={{ mb: 0.5 }}>
                        {t('diskSpace.intro', 'Free some space or grow these disks before updating them:')}
                    </Box>
                    {hosts.slice(0, SHOWN).map((h) => (
                        <Box key={String(h.id)}>
                            <Link component={RouterLink} to={`/hosts/${h.id}`}>{h.fqdn}</Link>
                            {': '}
                            {diskLine(t, h)}
                        </Box>
                    ))}
                    {total > SHOWN && (
                        <Box>
                            {t('diskSpace.more', 'and {{n}} more on the Hosts page', { n: total - SHOWN })}
                        </Box>
                    )}
                </>
            )}
        </Alert>
    );
};

export default DiskSpaceNotice;

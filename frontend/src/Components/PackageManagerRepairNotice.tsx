// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Hosts whose package manager needs repair, and those not safe to reboot
 * (2026-11-19).  Production: an "update all" left three hosts with a
 * half-configured kernel and no initramfs -- one reboot from not booting --
 * and the only sign was a chip in the Hosts grid.  This notice shows on the
 * host's page, the Updates page and the dashboard, with the repair one click
 * away.  Renders nothing when every host is healthy.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router';

import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';

import { doGetHostsSummary, doRepairPackageManagers, SysManageHost } from '../Services/hosts';
import { hasPermissionSync, SecurityRoles } from '../Services/permissions';

const SHOWN = 5;

const needsLook = (host: SysManageHost): boolean =>
    Boolean(host.package_manager_needs_repair || host.reboot_unsafe);

interface Props {
    /** One host (its own page); otherwise every host is fetched. */
    host?: SysManageHost | null;
    /** Called after a repair is requested, so the page can refresh. */
    onRepairStarted?: () => void;
}

const PackageManagerRepairNotice: React.FC<Props> = ({ host, onRepairStarted }) => {
    const { t } = useTranslation();
    const [hosts, setHosts] = useState<SysManageHost[]>([]);
    const [total, setTotal] = useState(0);
    const [message, setMessage] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (host !== undefined) {
            const shown = host && needsLook(host) ? [host] : [];
            setHosts(shown);
            setTotal(shown.length);
            return;
        }
        // The summary counts and names them: the host list is never loaded
        // for this (Phase 22.7: 15 MB at 20,000 hosts).
        let gone = false;
        doGetHostsSummary()
            .then((summary) => {
                if (gone) return;
                setHosts(summary.repair_hosts ?? []);
                setTotal(summary.package_manager_repair ?? 0);
            })
            .catch(() => { if (!gone) { setHosts([]); setTotal(0); } });
        return () => { gone = true; };
    }, [host]);

    const repairable = hosts.filter(
        (h) => h.package_manager_needs_repair && h.package_manager_repairable,
    );
    const canRepair = hasPermissionSync(SecurityRoles.APPLY_SOFTWARE_UPDATE);

    const repair = useCallback(async () => {
        setBusy(true);
        try {
            const result = await doRepairPackageManagers(repairable.map((h) => String(h.id)));
            setMessage(t('hosts.repairStarted', 'Package manager repair started on {{count}} host(s).', {
                count: result.started,
            }));
            onRepairStarted?.();
        } catch {
            setMessage(t('packageRepair.failed', 'The repair could not be started.'));
        } finally {
            setBusy(false);
        }
    }, [repairable, onRepairStarted, t]);

    if (hosts.length === 0) {
        return null;
    }
    const unsafe = hosts.filter((h) => h.reboot_unsafe);
    const single = host ? hosts[0] : null;
    const reasonOf = (h: SysManageHost) =>
        h.reboot_unsafe_reason || h.package_manager_repair_reason || '';

    return (
        <Alert
            severity={unsafe.length > 0 ? 'error' : 'warning'}
            sx={{ mb: 2 }}
            data-testid="package-manager-repair-notice"
            action={canRepair && repairable.length > 0 ? (
                <Button color="inherit" size="small" disabled={busy} onClick={repair}>
                    {t('hosts.repairPackageManager', 'Repair Package Manager')}
                </Button>
            ) : undefined}
        >
            <AlertTitle>
                {unsafe.length > 0
                    ? t('packageRepair.unsafeTitle', 'Do not reboot until the package manager is repaired')
                    : t('packageRepair.title', 'Package manager needs repair')}
            </AlertTitle>
            {single ? (
                <Box>{reasonOf(single)}</Box>
            ) : (
                <>
                    <Box sx={{ mb: 0.5 }}>
                        {t('packageRepair.intro', 'Updates sent to these hosts fail until it is repaired:')}
                    </Box>
                    {hosts.slice(0, SHOWN).map((h) => (
                        <Box key={String(h.id)}>
                            <Link component={RouterLink} to={`/hosts/${h.id}`}>{h.fqdn}</Link>
                            {': '}
                            {reasonOf(h)}
                        </Box>
                    ))}
                    {total > SHOWN && (
                        <Box>
                            {t('packageRepair.more', 'and {{n}} more on the Hosts page', {
                                n: total - SHOWN,
                            })}
                        </Box>
                    )}
                </>
            )}
            {message && <Box sx={{ mt: 1 }}>{message}</Box>}
        </Alert>
    );
};

export default PackageManagerRepairNotice;

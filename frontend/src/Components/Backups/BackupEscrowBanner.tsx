// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Pro+ break-glass escrow on the Backups page (ROADMAP 24.6, 2026-11-03):
// while the break-glass key export is missing, or older than an encrypted
// host or a key (encryption or signing), say so and link to a host's
// Encryption panel, where the export is made.  Nothing in Community, or with
// nothing to escrow (the server's ``applies``).

import React, { useEffect, useState } from 'react';
import { Alert, Button } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { getEscrowStatus, EscrowStatus } from '../../Services/backups';

/** The banner's text: why the export is out of date. */
export const escrowMessage = (
    t: (key: string, fallback: string, values?: Record<string, unknown>) => string,
    status: EscrowStatus,
): string => {
    if (!status.last_export) {
        return t('backups.escrow.never',
            'No break-glass key export has been made. If the SysManage server or OpenBAO is lost, the encrypted backups cannot be read without one.');
    }
    if (status.stale_hosts.length) {
        return t('backups.escrow.staleHosts',
            'The break-glass key export does not cover the newest keys of {{count}} encrypted host(s) ({{hosts}}). Make a new export and destroy the old one.',
            { count: status.stale_hosts.length, hosts: status.stale_hosts.join(', ') });
    }
    return t('backups.escrow.staleSigning',
        'Snapshot signing was turned on after the last break-glass key export. Make a new export so it carries the signing key.');
};

const BackupEscrowBanner: React.FC<{ refreshKey?: number }> = ({ refreshKey }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [status, setStatus] = useState<EscrowStatus | null>(null);

    useEffect(() => {
        let live = true;
        getEscrowStatus().then(found => { if (live) setStatus(found); }).catch(() => undefined);
        return () => { live = false; };
    }, [refreshKey]);

    if (!status?.applies || !status.stale) return null;
    return (
        <Alert severity="warning" sx={{ mb: 2 }}
            action={status.export_host_id ? (
                <Button color="inherit" size="small"
                    onClick={() => void navigate(`/hosts/${status.export_host_id}#backup`)}>
                    {t('backups.escrow.export', 'Export the keys')}
                </Button>
            ) : undefined}>
            {escrowMessage(t, status)}
        </Alert>
    );
};

export default BackupEscrowBanner;

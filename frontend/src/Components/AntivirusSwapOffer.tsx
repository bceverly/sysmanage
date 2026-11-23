// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * On a host without antivirus: if SysManage once added swap so it could run
 * ClamAV (Settings > Antivirus, "Add swap to hosts with too little memory for ClamAV"),
 * offer to remove that swap file now that ClamAV is gone.
 */

import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { getAntivirusSwap, removeAntivirusSwap } from '../Services/antivirusService';

const AntivirusSwapOffer: React.FC<{ hostId: string; canRemove: boolean }> = ({ hostId, canRemove }) => {
    const { t } = useTranslation();
    const [swapMb, setSwapMb] = useState<number | null>(null);
    const [done, setDone] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        getAntivirusSwap(hostId).then(setSwapMb).catch(() => setSwapMb(null));
    }, [hostId]);

    if (!swapMb) return null;
    if (done) {
        return (
            <Typography variant="body2" color="text.secondary" data-testid="antivirus-swap-offer">
                {t('antivirus.swap.removing', 'The swap file is being removed.')}
            </Typography>
        );
    }
    const remove = async () => {
        setError(null);
        try {
            await removeAntivirusSwap(hostId);
            setDone(true);
        } catch {
            setError(t('antivirus.swap.removeError', 'The swap file could not be removed.'));
        }
    };
    return (
        <Box data-testid="antivirus-swap-offer">
            <Typography variant="body2" color="text.secondary">
                {t('antivirus.swap.added', 'SysManage added {{size}} GB of swap to this host for ClamAV.',
                    { size: Math.round(swapMb / 1024) })}
                {canRemove && (
                    <Button size="small" sx={{ ml: 1 }} onClick={() => void remove()}>
                        {t('antivirus.swap.remove', 'Remove the swap')}
                    </Button>
                )}
            </Typography>
            {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
        </Box>
    );
};

export default AntivirusSwapOffer;

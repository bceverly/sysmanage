// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Curated rule packs: one shared copy, per-tenant choice.  A tenant switches
// a pack on or off, or opts single rules out; switching something off clears
// its findings at once (the server does that).

import React, { useState } from 'react';
import {
    Alert,
    Card,
    CardContent,
    Chip,
    FormControlLabel,
    Stack,
    Switch,
    Table,
    TableBody,
    TableCell,
    TableRow,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { advisorService, type AdvisorPack } from '../../Services/advisorService';
import { lensLabel } from './advisorLabels';

interface Props {
    packs: AdvisorPack[];
    onChanged: () => void;
}

const PackCard: React.FC<{ pack: AdvisorPack; onChoose: (pack: AdvisorPack, choice: object) => void }> = ({
    pack,
    onChoose,
}) => {
    const { t } = useTranslation();
    const toggleRule = (key: string, on: boolean) => {
        const disabled = new Set(pack.disabled_rules);
        if (on) disabled.delete(key);
        else disabled.add(key);
        onChoose(pack, { disabled_rules: Array.from(disabled) });
    };
    return (
        <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                    <Typography variant="h6">{pack.name}</Typography>
                    <Chip size="small" label={`v${pack.version}`} />
                    {pack.deprecated && (
                        <Chip size="small" color="warning" label={t('advisor.packs.deprecated', 'Withdrawn')} />
                    )}
                </Stack>
                {pack.description && <Typography variant="body2" sx={{ mb: 1 }}>{pack.description}</Typography>}
                <FormControlLabel
                    control={
                        <Switch
                            checked={pack.enabled}
                            disabled={pack.deprecated}
                            onChange={e => onChoose(pack, { enabled: e.target.checked })}
                        />
                    }
                    label={pack.choice === null
                        ? t('advisor.packs.followsDefault', 'Enabled for this tenant (following the default)')
                        : t('advisor.packs.chosen', 'Enabled for this tenant')}
                />
                <Table size="small">
                    <TableBody>
                        {pack.rules.map(rule => (
                            <TableRow key={rule.key}>
                                <TableCell padding="checkbox">
                                    <Switch
                                        size="small"
                                        checked={rule.enabled}
                                        disabled={!pack.enabled}
                                        onChange={e => toggleRule(rule.key, e.target.checked)}
                                        inputProps={{ 'aria-label': rule.key }}
                                    />
                                </TableCell>
                                <TableCell>{rule.title ?? rule.key}</TableCell>
                                <TableCell>{lensLabel(t, rule.lens)}</TableCell>
                                <TableCell><Typography variant="caption">{rule.key}</Typography></TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </CardContent>
        </Card>
    );
};

const AdvisorPacks: React.FC<Props> = ({ packs, onChanged }) => {
    const { t } = useTranslation();
    const [error, setError] = useState(false);
    const choose = async (pack: AdvisorPack, choice: object) => {
        setError(false);
        try {
            await advisorService.choosePack(pack.slug, choice);
        } catch {
            setError(true);
        }
        onChanged();
    };
    return (
        <>
            {error && (
                <Alert severity="error" sx={{ mb: 1 }}>
                    {t('advisor.packs.saveFailed', 'The change could not be saved.')}
                </Alert>
            )}
            {packs.length === 0 && (
                <Typography>{t('advisor.packs.none', 'No curated rule packs are installed.')}</Typography>
            )}
            {packs.map(p => <PackCard key={p.slug} pack={p} onChoose={choose} />)}
        </>
    );
};

export default AdvisorPacks;

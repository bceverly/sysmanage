// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Hardware events (Phase 23.1 S4): each state change -- a drive turning
// warning, a pool degrading, a drive no longer reported -- newest first, with
// acknowledge / resolve and a note for those who hold Manage Hardware Health.

import React, { useEffect, useState } from 'react';
import {
    Button,
    Checkbox,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Link,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from '@mui/material';
import { Link as RouterLink } from 'react-router';
import { useTranslation } from 'react-i18next';
import { hasPermission, SecurityRoles } from '../../Services/permissions';
import { changeHardwareEvent } from '../../Services/hardwareHealth';
import type { HardwareEvent } from '../../Services/hardwareHealth';
import { kindLabel, reasonsText, statusColor, transitionText } from './hardwareHealthLabels';
import HardwareEventsBulkBar, { useEventSelection } from './HardwareEventsBulkBar';

type Action = 'acknowledge' | 'resolve';

// See the action cell below: these two buttons must not wrap.
const NO_WRAP = { whiteSpace: 'nowrap', overflowWrap: 'normal' } as const;

const when = (iso: string | null): string => (iso ? new Date(`${iso}Z`).toLocaleString() : '');

const NoteDialog: React.FC<{
    action: Action | null;
    onCancel: () => void;
    onConfirm: (note: string) => void;
}> = ({ action, onCancel, onConfirm }) => {
    const { t } = useTranslation();
    const [note, setNote] = useState('');
    useEffect(() => setNote(''), [action]);
    const title = action === 'resolve'
        ? t('hardwareHealth.events.resolveTitle', 'Resolve this event')
        : t('hardwareHealth.events.acknowledgeTitle', 'Acknowledge this event');
    return (
        <Dialog open={action !== null} onClose={onCancel} fullWidth maxWidth="sm">
            <DialogTitle>{title}</DialogTitle>
            <DialogContent>
                <TextField
                    autoFocus
                    fullWidth
                    multiline
                    minRows={2}
                    margin="dense"
                    label={t('hardwareHealth.events.note', 'Note (optional)')}
                    value={note}
                    onChange={e => setNote(e.target.value.slice(0, 500))}
                />
            </DialogContent>
            <DialogActions>
                <Button onClick={onCancel}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" onClick={() => onConfirm(note)}>{title}</Button>
            </DialogActions>
        </Dialog>
    );
};

const EventState: React.FC<{ event: HardwareEvent }> = ({ event }) => {
    const { t } = useTranslation();
    if (event.resolved_at) {
        return (
            <Typography variant="caption" color="text.secondary">
                {t('hardwareHealth.events.resolvedBy', 'Resolved by {{user}}', { user: event.resolved_by ?? '' })}
            </Typography>
        );
    }
    if (event.acknowledged_at) {
        return (
            <Typography variant="caption" color="text.secondary">
                {t('hardwareHealth.events.acknowledgedBy', 'Acknowledged by {{user}}', { user: event.acknowledged_by ?? '' })}
            </Typography>
        );
    }
    return null;
};

const HardwareEventsList: React.FC<{
    events: HardwareEvent[];
    showHost?: boolean;
    onChanged?: () => void;
    /** Open events in all; more than listed offers "Select all N". */
    total?: number;
    /** Scopes "all open" to one host. */
    hostId?: string;
}> = ({ events, showHost = false, onChanged, total, hostId }) => {
    const { t } = useTranslation();
    const [canChange, setCanChange] = useState(false);
    const selection = useEventSelection(events);
    const bulk = canChange && events.some(selection.selectable);
    const [pending, setPending] = useState<{ event: HardwareEvent; action: Action } | null>(null);

    useEffect(() => {
        void hasPermission(SecurityRoles.MANAGE_HARDWARE_HEALTH)
            .then(setCanChange)
            .catch(() => setCanChange(false));
    }, []);

    const confirm = async (note: string) => {
        if (!pending) {
            return;
        }
        try {
            await changeHardwareEvent(pending.event.id, pending.action, note);
        } finally {
            setPending(null);
            onChanged?.();
        }
    };

    if (events.length === 0) {
        return (
            <Typography variant="body2" color="text.secondary">
                {t('hardwareHealth.events.none', 'No hardware events.')}
            </Typography>
        );
    }
    return (
        <>
            {bulk && (
                <HardwareEventsBulkBar
                    selection={selection}
                    total={total ?? events.filter(selection.selectable).length}
                    hostId={hostId}
                    onChanged={onChanged}
                />
            )}
            <Table size="small">
                <TableHead>
                    <TableRow>
                        {bulk && (
                            <TableCell padding="checkbox">
                                <Checkbox
                                    size="small"
                                    checked={selection.pageSelected}
                                    indeterminate={selection.somePageSelected}
                                    onChange={selection.togglePage}
                                    slotProps={{ input: { 'aria-label': t('hardwareHealth.events.selectPage', 'Select all events on this page') } }}
                                />
                            </TableCell>
                        )}
                        <TableCell>{t('hardwareHealth.events.when', 'Time')}</TableCell>
                        {showHost && <TableCell>{t('hardwareHealth.events.host', 'Host')}</TableCell>}
                        <TableCell>{t('hardwareHealth.events.component', 'Component')}</TableCell>
                        <TableCell>{t('hardwareHealth.events.change', 'Change')}</TableCell>
                        <TableCell>{t('hardwareHealth.events.why', 'Reason')}</TableCell>
                        <TableCell />
                    </TableRow>
                </TableHead>
                <TableBody>
                    {events.map(event => (
                        <TableRow key={event.id} selected={selection.selected.has(event.id)}>
                            {bulk && (
                                <TableCell padding="checkbox">
                                    {selection.selectable(event) && (
                                        <Checkbox
                                            size="small"
                                            checked={selection.selected.has(event.id)}
                                            onChange={() => selection.toggle(event.id)}
                                            slotProps={{ input: { 'aria-label': t('hardwareHealth.events.selectEvent', 'Select this event') } }}
                                        />
                                    )}
                                </TableCell>
                            )}
                            <TableCell>{when(event.occurred_at)}</TableCell>
                            {showHost && (
                                <TableCell>
                                    <Link component={RouterLink} to={`/hosts/${event.host_id}`}>
                                        {event.fqdn ?? event.host_id}
                                    </Link>
                                </TableCell>
                            )}
                            <TableCell>
                                {event.kind === 'system'
                                    ? kindLabel(t, event.kind)
                                    : `${kindLabel(t, event.kind)}: ${event.name ?? event.component_id}`}
                            </TableCell>
                            <TableCell>
                                <Chip size="small" color={statusColor(event.to_state)} label={transitionText(t, event)} />
                            </TableCell>
                            <TableCell>
                                <Typography variant="body2">{reasonsText(t, event.reasons)}</Typography>
                                {event.note && (
                                    <Typography variant="caption" color="text.secondary">{event.note}</Typography>
                                )}
                            </TableCell>
                            {/* never wrap the actions: a long reason squeezed "Acknowledge"
                                into "ACKNOWL / EDGE" on the host card.  The theme lets every
                                Button wrap anywhere (long translations), and a Button's own
                                style beats the cell's, so the buttons say nowrap themselves;
                                in a table the reason column wraps instead. */}
                            <TableCell align="right" sx={{ whiteSpace: 'nowrap', width: '1%' }}>
                                <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
                                    <EventState event={event} />
                                    {canChange && !event.acknowledged_at && (
                                        <Button size="small" sx={NO_WRAP} onClick={() => setPending({ event, action: 'acknowledge' })}>
                                            {t('hardwareHealth.events.acknowledge', 'Acknowledge')}
                                        </Button>
                                    )}
                                    {canChange && !event.resolved_at && (
                                        <Button size="small" sx={NO_WRAP} onClick={() => setPending({ event, action: 'resolve' })}>
                                            {t('hardwareHealth.events.resolve', 'Resolve')}
                                        </Button>
                                    )}
                                </Stack>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
            <NoteDialog
                action={pending?.action ?? null}
                onCancel={() => setPending(null)}
                onConfirm={note => void confirm(note)}
            />
        </>
    );
};

export default HardwareEventsList;

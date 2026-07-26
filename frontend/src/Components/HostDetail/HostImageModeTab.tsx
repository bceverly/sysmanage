// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Image-mode (bootc / rpm-ostree) host management tab.  Detection/display is
// always visible for image-mode hosts; the stage/apply/rollback ACTIONS are
// gated on the Enterprise ``image_mode_engine`` module license.  Apply and
// Rollback reboot the host, so both are confirmed via a dialog first.

import React, { useState } from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Grid,
    Chip,
    Button,
    CircularProgress,
    Alert,
    Snackbar,
    Tooltip,
    Table,
    TableBody,
    TableRow,
    TableCell,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogContentText,
    DialogActions,
} from '@mui/material';
import LayersIcon from '@mui/icons-material/Layers';
import PublishIcon from '@mui/icons-material/Publish';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import HistoryIcon from '@mui/icons-material/History';
import { useTranslation } from 'react-i18next';
import { SysManageHost } from '../../Services/hosts';
import { stageImage, applyImage, rollbackImage } from '../../Services/imageMode';
import useModuleLicensed from '../../hooks/useModuleLicensed';

interface HostImageModeTabProps {
    host: SysManageHost;
}

type SnackbarSeverity = 'success' | 'error';
type PendingAction = 'apply' | 'rollback' | null;

// Shorten a ``sha256:<hex>`` digest to ``sha256:`` + first 12 hex chars.
const truncateDigest = (digest: string): string => {
    const idx = digest.indexOf(':');
    if (idx === -1) {
        return digest.slice(0, 12);
    }
    const algo = digest.slice(0, idx + 1);
    const hex = digest.slice(idx + 1);
    return `${algo}${hex.slice(0, 12)}`;
};

const HostImageModeTab: React.FC<HostImageModeTabProps> = ({ host }) => {
    const { t } = useTranslation();
    const licensed = useModuleLicensed('image_mode_engine');

    const [staging, setStaging] = useState<boolean>(false);
    const [applying, setApplying] = useState<boolean>(false);
    const [rollingBack, setRollingBack] = useState<boolean>(false);
    const [confirmAction, setConfirmAction] = useState<PendingAction>(null);

    const [snackbarOpen, setSnackbarOpen] = useState<boolean>(false);
    const [snackbarMessage, setSnackbarMessage] = useState<string>('');
    const [snackbarSeverity, setSnackbarSeverity] = useState<SnackbarSeverity>('success');

    const busy = staging || applying || rollingBack;
    const hasStaged = Boolean(host.staged_image_ref);
    const rollbackAvailable = Boolean(host.rollback_available);

    const notify = (message: string, severity: SnackbarSeverity) => {
        setSnackbarMessage(message);
        setSnackbarSeverity(severity);
        setSnackbarOpen(true);
    };

    const handleStage = async () => {
        if (!host.id) return;
        setStaging(true);
        try {
            await stageImage(host.id);
            notify(t('hostDetail.imageMode.stageSuccess', 'Image stage requested'), 'success');
        } catch {
            notify(t('hostDetail.imageMode.stageError', 'Failed to stage image'), 'error');
        } finally {
            setStaging(false);
        }
    };

    const handleConfirmApply = async () => {
        setConfirmAction(null);
        if (!host.id) return;
        setApplying(true);
        try {
            await applyImage(host.id);
            notify(t('hostDetail.imageMode.applySuccess', 'Image apply requested (host will reboot)'), 'success');
        } catch {
            notify(t('hostDetail.imageMode.applyError', 'Failed to apply image'), 'error');
        } finally {
            setApplying(false);
        }
    };

    const handleConfirmRollback = async () => {
        setConfirmAction(null);
        if (!host.id) return;
        setRollingBack(true);
        try {
            await rollbackImage(host.id);
            notify(t('hostDetail.imageMode.rollbackSuccess', 'Image rollback requested (host will reboot)'), 'success');
        } catch {
            notify(t('hostDetail.imageMode.rollbackError', 'Failed to roll back image'), 'error');
        } finally {
            setRollingBack(false);
        }
    };

    const handleCloseSnackbar = () => setSnackbarOpen(false);

    const renderDigest = (digest?: string) => {
        if (!digest) {
            return <>—</>;
        }
        return (
            <Tooltip title={digest}>
                <Typography component="span" variant="body2" sx={{ fontFamily: 'monospace' }}>
                    {truncateDigest(digest)}
                </Typography>
            </Tooltip>
        );
    };

    // A single action button, wrapped in a Tooltip explaining the license gate
    // when the Enterprise module isn't present.  Detection stays visible; only
    // the actions gate.
    const actionButton = (button: React.ReactElement) => {
        if (licensed) {
            return button;
        }
        return (
            <Tooltip title={t('hostDetail.imageMode.enterpriseOnly', 'Image mode actions require an Enterprise license')}>
                <span>{button}</span>
            </Tooltip>
        );
    };

    return (
        <Grid container spacing={3}>
            <Grid size={{ xs: 12 }}>
                <Card>
                    <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                            <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <LayersIcon />
                                {t('hostDetail.imageMode.title', 'Image Mode')}
                            </Typography>
                            <Box sx={{ display: 'flex', gap: 1 }}>
                                {actionButton(
                                    <Button
                                        variant="outlined"
                                        color="primary"
                                        size="small"
                                        onClick={handleStage}
                                        disabled={!licensed || busy || !host.active}
                                        startIcon={staging ? <CircularProgress size={16} /> : <PublishIcon />}
                                    >
                                        {t('hostDetail.imageMode.stage', 'Stage')}
                                    </Button>,
                                )}
                                {actionButton(
                                    <Button
                                        variant="outlined"
                                        color="warning"
                                        size="small"
                                        onClick={() => setConfirmAction('apply')}
                                        disabled={!licensed || busy || !host.active}
                                        startIcon={applying ? <CircularProgress size={16} /> : <RestartAltIcon />}
                                    >
                                        {t('hostDetail.imageMode.apply', 'Apply')}
                                    </Button>,
                                )}
                                {actionButton(
                                    <Button
                                        variant="outlined"
                                        color="warning"
                                        size="small"
                                        onClick={() => setConfirmAction('rollback')}
                                        disabled={!licensed || busy || !host.active || !rollbackAvailable}
                                        startIcon={rollingBack ? <CircularProgress size={16} /> : <HistoryIcon />}
                                    >
                                        {t('hostDetail.imageMode.rollback', 'Rollback')}
                                    </Button>,
                                )}
                            </Box>
                        </Box>

                        {!licensed && (
                            <Alert severity="info" sx={{ mb: 2 }}>
                                {t('hostDetail.imageMode.enterpriseNotice', 'Staging, applying, and rolling back images is an Enterprise feature. The current image details are shown below.')}
                            </Alert>
                        )}

                        <Grid container spacing={2} sx={{ mt: 1 }}>
                            <Grid size={{ xs: 12, md: 6 }}>
                                <Card variant="outlined" sx={{ mb: 2 }}>
                                    <CardContent>
                                        <Typography variant="h6" gutterBottom>
                                            {t('hostDetail.imageMode.bootedImage', 'Booted Image')}
                                        </Typography>
                                        <Table size="small">
                                            <TableBody>
                                                <TableRow>
                                                    <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                        {t('hostDetail.imageMode.backend', 'Backend')}
                                                    </TableCell>
                                                    <TableCell>
                                                        <Chip
                                                            label={host.image_backend || t('common.unknown', 'Unknown')}
                                                            color="primary"
                                                            size="small"
                                                        />
                                                    </TableCell>
                                                </TableRow>
                                                <TableRow>
                                                    <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                        {t('hostDetail.imageMode.imageRef', 'Image Reference')}
                                                    </TableCell>
                                                    <TableCell sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                                                        {host.booted_image_ref || '—'}
                                                    </TableCell>
                                                </TableRow>
                                                <TableRow>
                                                    <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                        {t('hostDetail.imageMode.digest', 'Digest')}
                                                    </TableCell>
                                                    <TableCell>
                                                        {renderDigest(host.booted_image_digest)}
                                                    </TableCell>
                                                </TableRow>
                                                <TableRow>
                                                    <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                        {t('hostDetail.imageMode.rollbackAvailable', 'Rollback Available')}
                                                    </TableCell>
                                                    <TableCell>
                                                        <Chip
                                                            label={rollbackAvailable ? t('common.yes', 'Yes') : t('common.no', 'No')}
                                                            color={rollbackAvailable ? 'success' : 'default'}
                                                            size="small"
                                                        />
                                                    </TableCell>
                                                </TableRow>
                                            </TableBody>
                                        </Table>
                                    </CardContent>
                                </Card>
                            </Grid>

                            <Grid size={{ xs: 12, md: 6 }}>
                                <Card variant="outlined">
                                    <CardContent>
                                        <Typography variant="h6" gutterBottom>
                                            {t('hostDetail.imageMode.stagedImage', 'Staged Image')}
                                        </Typography>
                                        {hasStaged ? (
                                            <>
                                                <Alert severity="warning" sx={{ mb: 2 }}>
                                                    {t('hostDetail.imageMode.pendingReboot', 'Pending — reboot to apply')}
                                                </Alert>
                                                <Table size="small">
                                                    <TableBody>
                                                        <TableRow>
                                                            <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                {t('hostDetail.imageMode.imageRef', 'Image Reference')}
                                                            </TableCell>
                                                            <TableCell sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                                                                {host.staged_image_ref || '—'}
                                                            </TableCell>
                                                        </TableRow>
                                                        <TableRow>
                                                            <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                {t('hostDetail.imageMode.digest', 'Digest')}
                                                            </TableCell>
                                                            <TableCell>
                                                                {renderDigest(host.staged_image_digest)}
                                                            </TableCell>
                                                        </TableRow>
                                                    </TableBody>
                                                </Table>
                                            </>
                                        ) : (
                                            <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic' }}>
                                                {t('hostDetail.imageMode.noStagedImage', 'No image staged')}
                                            </Typography>
                                        )}
                                    </CardContent>
                                </Card>
                            </Grid>
                        </Grid>
                    </CardContent>
                </Card>
            </Grid>

            {/* Reboot confirmation for Apply / Rollback */}
            <Dialog open={confirmAction !== null} onClose={() => setConfirmAction(null)}>
                <DialogTitle>
                    {confirmAction === 'rollback'
                        ? t('hostDetail.imageMode.confirmRollbackTitle', 'Roll back image?')
                        : t('hostDetail.imageMode.confirmApplyTitle', 'Apply staged image?')}
                </DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {confirmAction === 'rollback'
                            ? t('hostDetail.imageMode.confirmRollbackMessage', 'This rolls the host back to its prior image and REBOOTS it. Continue?')
                            : t('hostDetail.imageMode.confirmApplyMessage', 'This applies the staged image and REBOOTS the host. Continue?')}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setConfirmAction(null)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        color="warning"
                        onClick={confirmAction === 'rollback' ? handleConfirmRollback : handleConfirmApply}
                    >
                        {t('common.confirm', 'Confirm')}
                    </Button>
                </DialogActions>
            </Dialog>

            <Snackbar
                open={snackbarOpen}
                autoHideDuration={6000}
                onClose={handleCloseSnackbar}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            >
                <Alert onClose={handleCloseSnackbar} severity={snackbarSeverity} sx={{ width: '100%' }}>
                    {snackbarMessage}
                </Alert>
            </Snackbar>
        </Grid>
    );
};

export default HostImageModeTab;

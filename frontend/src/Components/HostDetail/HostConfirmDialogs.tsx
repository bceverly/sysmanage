// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Grid,
    Chip,
    Button,
    CircularProgress,
    Paper,
    IconButton,
    Alert,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogContentText,
    DialogActions,
    Table,
    TableBody,
    TableRow,
    TableCell,
    TableHead,
    TextField,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import WarningIcon from '@mui/icons-material/Warning';
import { useTranslation } from 'react-i18next';
import { SysManageHost, RebootPreCheckResponse, DiagnosticDetailResponse } from '../../Services/hosts';
import { ChildHost } from './hostDetailTypes';
import { formatDate } from './hostDetailHelpers';

interface HostConfirmDialogsProps {
    host: SysManageHost | null;
    dialogOpen: boolean;
    dialogTitle: string;
    dialogContent: string;
    handleCloseDialog: () => void;
    rebootConfirmOpen: boolean;
    setRebootConfirmOpen: (value: boolean) => void;
    rebootPreCheckData: RebootPreCheckResponse | null;
    setRebootPreCheckData: (value: RebootPreCheckResponse | null) => void;
    rebootPreCheckLoading: boolean;
    handleRebootConfirm: () => void;
    shutdownConfirmOpen: boolean;
    setShutdownConfirmOpen: (value: boolean) => void;
    handleShutdownConfirm: () => void;
    hostnameEditOpen: boolean;
    setHostnameEditOpen: (value: boolean) => void;
    newHostname: string;
    setNewHostname: (value: string) => void;
    hostnameEditLoading: boolean;
    handleHostnameChange: () => void;
    deleteConfirmOpen: boolean;
    handleCancelDelete: () => void;
    handleConfirmDelete: () => void;
    deleteChildHostConfirmOpen: boolean;
    childHostToDelete: ChildHost | null;
    handleChildHostDeleteCancel: () => void;
    handleChildHostDelete: () => void;
    diagnosticDetailOpen: boolean;
    setDiagnosticDetailOpen: (value: boolean) => void;
    diagnosticDetailLoading: boolean;
    selectedDiagnostic: DiagnosticDetailResponse | null;
    ubuntuProDetachConfirmOpen: boolean;
    handleCancelUbuntuProDetach: () => void;
    handleConfirmUbuntuProDetach: () => void;
    ubuntuProTokenDialog: boolean;
    ubuntuProToken: string;
    setUbuntuProToken: (value: string) => void;
    handleUbuntuProTokenCancel: () => void;
    handleUbuntuProTokenSubmit: () => void;
}

const HostConfirmDialogs: React.FC<HostConfirmDialogsProps> = ({
    host,
    dialogOpen,
    dialogTitle,
    dialogContent,
    handleCloseDialog,
    rebootConfirmOpen,
    setRebootConfirmOpen,
    rebootPreCheckData,
    setRebootPreCheckData,
    rebootPreCheckLoading,
    handleRebootConfirm,
    shutdownConfirmOpen,
    setShutdownConfirmOpen,
    handleShutdownConfirm,
    hostnameEditOpen,
    setHostnameEditOpen,
    newHostname,
    setNewHostname,
    hostnameEditLoading,
    handleHostnameChange,
    deleteConfirmOpen,
    handleCancelDelete,
    handleConfirmDelete,
    deleteChildHostConfirmOpen,
    childHostToDelete,
    handleChildHostDeleteCancel,
    handleChildHostDelete,
    diagnosticDetailOpen,
    setDiagnosticDetailOpen,
    diagnosticDetailLoading,
    selectedDiagnostic,
    ubuntuProDetachConfirmOpen,
    handleCancelUbuntuProDetach,
    handleConfirmUbuntuProDetach,
    ubuntuProTokenDialog,
    ubuntuProToken,
    setUbuntuProToken,
    handleUbuntuProTokenCancel,
    handleUbuntuProTokenSubmit,
}) => {
    const { t } = useTranslation();
    return (
        <>
            {/* Dialog for Additional Details */}
            <Dialog
                open={dialogOpen}
                onClose={handleCloseDialog}
                maxWidth="md"
                fullWidth
                slotProps={{
                    paper: { sx: { backgroundColor: 'grey.900' } }
                }}
            >
                <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 'bold', fontSize: '1.25rem' }}>{dialogTitle}</Typography>
                    <IconButton onClick={handleCloseDialog} size="small">
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent>
                    <Typography variant="body2" component="pre" sx={{ 
                        fontSize: '0.75rem', 
                        whiteSpace: 'pre-wrap', 
                        wordBreak: 'break-word',
                        backgroundColor: 'grey.800',
                        p: 2,
                        borderRadius: 1,
                        overflow: 'auto'
                    }}>
                        {dialogContent}
                    </Typography>
                </DialogContent>
            </Dialog>

            {/* Reboot Confirmation Dialog */}
            <Dialog
                open={rebootConfirmOpen}
                onClose={() => { setRebootConfirmOpen(false); setRebootPreCheckData(null); }}
                aria-labelledby="reboot-dialog-title"
                aria-describedby="reboot-dialog-description"
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle id="reboot-dialog-title">
                    {t('hosts.confirmReboot', 'Confirm System Reboot')}
                </DialogTitle>
                <DialogContent>
                    {rebootPreCheckLoading && (
                        <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
                            <CircularProgress size={24} />
                        </Box>
                    )}
                    {!rebootPreCheckLoading && rebootPreCheckData?.has_running_children && (
                        <>
                            {rebootPreCheckData.has_container_engine ? (
                                <Alert severity="info" sx={{ mb: 2 }}>
                                    {t('hosts.rebootOrchestration.orchestratedInfo', 'This host has {{count}} running child host(s). SysManage will safely stop them before rebooting and automatically restart them afterward.', { count: rebootPreCheckData.running_count })}
                                </Alert>
                            ) : (
                                <Alert severity="warning" sx={{ mb: 2 }}>
                                    {t('hosts.rebootOrchestration.ungracefulWarning', 'This host has {{count}} running child host(s) that will be ungracefully terminated during reboot. Upgrade to SysManage Professional+ for orchestrated safe reboot.', { count: rebootPreCheckData.running_count })}
                                </Alert>
                            )}
                            <Typography variant="subtitle2" sx={{ mb: 1 }}>
                                {t('hosts.rebootOrchestration.runningChildren', 'Running child hosts:')}
                            </Typography>
                            <Table size="small" sx={{ mb: 2 }}>
                                <TableHead>
                                    <TableRow>
                                        <TableCell>{t('hosts.rebootOrchestration.childName', 'Name')}</TableCell>
                                        <TableCell>{t('hosts.rebootOrchestration.childType', 'Type')}</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {rebootPreCheckData.running_children.map((child) => (
                                        <TableRow key={child.id}>
                                            <TableCell>{child.child_name}</TableCell>
                                            <TableCell>
                                                <Chip label={child.child_type.toUpperCase()} size="small" />
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                            <Typography id="reboot-dialog-description" variant="body2" color="text.secondary">
                                {rebootPreCheckData.has_container_engine
                                    ? t('hosts.rebootOrchestration.proceedOrchestrated', 'Click "Orchestrated Reboot" to safely reboot {{hostname}}.', { hostname: host?.fqdn })
                                    : t('hosts.rebootOrchestration.proceedAnyway', 'Click "Reboot Anyway" to reboot {{hostname}} without stopping child hosts first.', { hostname: host?.fqdn })
                                }
                            </Typography>
                        </>
                    )}
                    {!rebootPreCheckLoading && !rebootPreCheckData?.has_running_children && (
                        <Typography id="reboot-dialog-description">
                            {t('hosts.confirmRebootMessage', 'Are you sure you want to reboot {{hostname}}? The system will be unavailable for a few minutes.', { hostname: host?.fqdn })}
                        </Typography>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => { setRebootConfirmOpen(false); setRebootPreCheckData(null); }}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    {!rebootPreCheckLoading && (
                        <Button onClick={handleRebootConfirm} color="warning" variant="contained">
                            {(() => {
                                if (!rebootPreCheckData?.has_running_children) {
                                    return t('hosts.reboot', 'Reboot');
                                }
                                if (rebootPreCheckData.has_container_engine) {
                                    return t('hosts.rebootOrchestration.orchestratedRebootButton', 'Orchestrated Reboot');
                                }
                                return t('hosts.rebootOrchestration.rebootAnywayButton', 'Reboot Anyway');
                            })()}
                        </Button>
                    )}
                </DialogActions>
            </Dialog>

            {/* Shutdown Confirmation Dialog */}
            <Dialog
                open={shutdownConfirmOpen}
                onClose={() => setShutdownConfirmOpen(false)}
                aria-labelledby="shutdown-dialog-title"
                aria-describedby="shutdown-dialog-description"
            >
                <DialogTitle id="shutdown-dialog-title">
                    {t('hosts.confirmShutdown', 'Confirm System Shutdown')}
                </DialogTitle>
                <DialogContent>
                    <Typography id="shutdown-dialog-description">
                        {t('hosts.confirmShutdownMessage', 'Are you sure you want to shutdown {{hostname}}? The system will need to be manually restarted.', { hostname: host?.fqdn })}
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setShutdownConfirmOpen(false)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button onClick={handleShutdownConfirm} color="error" variant="contained">
                        {t('hosts.shutdown', 'Shutdown')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Edit Hostname Dialog */}
            <Dialog
                open={hostnameEditOpen}
                onClose={() => setHostnameEditOpen(false)}
                aria-labelledby="hostname-edit-dialog-title"
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle id="hostname-edit-dialog-title">
                    {t('hostDetail.editHostname', 'Edit Hostname')}
                </DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        margin="dense"
                        id="hostname"
                        label={t('hostDetail.hostname', 'Hostname')}
                        type="text"
                        fullWidth
                        variant="outlined"
                        value={newHostname}
                        onChange={(e) => setNewHostname(e.target.value)}
                        helperText={t('hostDetail.hostnameHelp', 'Enter a short hostname or fully qualified domain name (FQDN)')}
                        disabled={hostnameEditLoading}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setHostnameEditOpen(false)} disabled={hostnameEditLoading}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleHostnameChange}
                        color="primary"
                        variant="contained"
                        disabled={hostnameEditLoading || !newHostname.trim()}
                    >
                        {hostnameEditLoading ? <CircularProgress size={24} /> : t('common.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Delete Confirmation Dialog */}
            <Dialog
                open={deleteConfirmOpen}
                onClose={handleCancelDelete}
                maxWidth="sm"
                fullWidth
                slotProps={{
                    paper: { sx: { backgroundColor: 'grey.900' } }
                }}
            >
                <DialogTitle sx={{ fontWeight: 'bold', fontSize: '1.25rem' }}>
                    {t('hostDetail.deleteDiagnosticConfirm', 'Delete Diagnostic Report')}
                </DialogTitle>
                <DialogContent>
                    <Typography>
                        {t('hostDetail.deleteDiagnosticMessage', 'Are you sure you want to delete this diagnostic report? This action cannot be undone.')}
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCancelDelete}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button onClick={handleConfirmDelete} color="error" variant="contained">
                        {t('hosts.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Delete/Cancel Child Host Confirmation Dialog */}
            <Dialog
                open={deleteChildHostConfirmOpen}
                onClose={handleChildHostDeleteCancel}
                maxWidth="sm"
                fullWidth
                slotProps={{
                    paper: { sx: { backgroundColor: 'grey.900' } }
                }}
            >
                <DialogTitle sx={{ fontWeight: 'bold', fontSize: '1.25rem', display: 'flex', alignItems: 'center', gap: 1 }}>
                    <WarningIcon color={childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending' ? 'warning' : 'error'} />
                    {childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending'
                        ? t('hostDetail.cancelChildHostConfirmTitle', 'Cancel Child Host Creation')
                        : t('hostDetail.deleteChildHostConfirmTitle', 'Delete Child Host')}
                </DialogTitle>
                <DialogContent>
                    {childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending' ? (
                        <>
                            <Alert severity="warning" sx={{ mb: 2 }}>
                                {t('hostDetail.cancelChildHostWarning', 'This will cancel the child host creation.')}
                            </Alert>
                            <Typography variant="body1" sx={{ mb: 2 }}>
                                {t('hostDetail.cancelChildHostMessage', 'Are you sure you want to cancel the creation of "{{name}}"?', { name: childHostToDelete?.child_name })}
                            </Typography>
                            <Typography variant="body2" color="textSecondary">
                                {t('hostDetail.cancelChildHostNote', 'The creation record will be removed from the database. If the agent is currently creating this child host, the partial installation may need to be cleaned up manually.')}
                            </Typography>
                        </>
                    ) : (
                        <>
                            <Alert severity="error" sx={{ mb: 2 }}>
                                {t('hostDetail.deleteChildHostWarning', 'This action is irreversible!')}
                            </Alert>
                            <Typography variant="body1" sx={{ mb: 2 }}>
                                {t('hostDetail.deleteChildHostMessage', 'Are you sure you want to delete the child host "{{name}}"?', { name: childHostToDelete?.child_name })}
                            </Typography>
                            <Typography variant="body2" color="textSecondary">
                                {t('hostDetail.deleteChildHostDataWarning', 'This will permanently delete the virtual machine and ALL of its data, including:')}
                            </Typography>
                            <Box component="ul" sx={{ pl: 2, mt: 1, color: 'text.secondary' }}>
                                <li>{t('hostDetail.deleteChildHostDataItem1', 'All files and user data')}</li>
                                <li>{t('hostDetail.deleteChildHostDataItem2', 'Installed applications')}</li>
                                <li>{t('hostDetail.deleteChildHostDataItem3', 'System configuration')}</li>
                            </Box>
                        </>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleChildHostDeleteCancel}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button onClick={handleChildHostDelete} color={childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending' ? 'warning' : 'error'} variant="contained">
                        {childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending'
                            ? t('hostDetail.cancelChildHostConfirmButton', 'Cancel Creation')
                            : t('hostDetail.deleteChildHostConfirmButton', 'Delete Permanently')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Diagnostic Detail Modal */}
            <Dialog
                open={diagnosticDetailOpen}
                onClose={() => setDiagnosticDetailOpen(false)}
                maxWidth="lg"
                fullWidth
                scroll="paper"
            >
                <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 'bold', fontSize: '1.25rem' }}>
                        {t('hostDetail.diagnosticDetailTitle', 'Diagnostic Report Details')}
                        {selectedDiagnostic && ` #${selectedDiagnostic.collection_id?.substring(0, 8) || t('common.unknown', 'Unknown')}`}
                    </Typography>
                    <IconButton onClick={() => setDiagnosticDetailOpen(false)} size="small">
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent sx={{ p: 3 }}>
                    {(() => {
                        if (diagnosticDetailLoading) {
                            return (
                                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                                    <CircularProgress />
                                </Box>
                            );
                        }
                        if (selectedDiagnostic) {
                            return (
                                <Box>
                                    {/* Diagnostic Report Metadata */}
                                    <Card sx={{ mb: 3, backgroundColor: 'grey.800' }}>
                                        <CardContent>
                                            <Grid container spacing={2}>
                                                <Grid size={{ xs: 12, sm: 6 }}>
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.collectionId', 'Collection ID')}
                                                    </Typography>
                                                    <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                                                        {selectedDiagnostic.collection_id}
                                                    </Typography>
                                                </Grid>
                                                <Grid size={{ xs: 12, sm: 6 }}>
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.collectionStatus', 'Status')}
                                                    </Typography>
                                                    <Chip
                                                        label={selectedDiagnostic.status}
                                                        color={selectedDiagnostic.status === 'completed' ? 'success' : 'warning'}
                                                        size="small"
                                                    />
                                                </Grid>
                                                <Grid size={{ xs: 12, sm: 6 }}>
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.requestedAt', 'Requested At')}
                                                    </Typography>
                                                    <Typography variant="body1">
                                                        {formatDate(t, selectedDiagnostic.requested_at)}
                                                    </Typography>
                                                </Grid>
                                                <Grid size={{ xs: 12, sm: 6 }}>
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.completedAt', 'Completed At')}
                                                    </Typography>
                                                    <Typography variant="body1">
                                                        {formatDate(t, selectedDiagnostic.completed_at)}
                                                    </Typography>
                                                </Grid>
                                            </Grid>
                                        </CardContent>
                                    </Card>

                                    {/* Diagnostic Data Sections */}
                                    {selectedDiagnostic.diagnostic_data && (
                                        <Box>
                                            {Object.entries(selectedDiagnostic.diagnostic_data).map(([key, value]) => {
                                                if (!value || (typeof value === 'object' && Object.keys(value).length === 0)) return null;

                                                const sectionTitle = t(`hostDetail.${key}`, key.replaceAll('_', ' ').replaceAll(/\b\w/g, l => l.toUpperCase()));

                                                return (
                                                    <Card key={key} sx={{ mb: 2, backgroundColor: 'grey.700' }}>
                                                        <CardContent>
                                                            <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 'bold', fontSize: '1.1rem' }}>
                                                                {sectionTitle}
                                                            </Typography>
                                                            <Paper sx={{ p: 2, backgroundColor: 'grey.900', color: 'white', maxHeight: 300, overflow: 'auto' }}>
                                                                <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                                    {typeof value === 'string'
                                                                        ? value
                                                                        : JSON.stringify(value, null, 2)
                                                                    }
                                                                </Typography>
                                                            </Paper>
                                                        </CardContent>
                                                    </Card>
                                                );
                                            })}
                                        </Box>
                                    )}

                                    {(!selectedDiagnostic.diagnostic_data || Object.keys(selectedDiagnostic.diagnostic_data).length === 0) && (
                                        <Box sx={{ textAlign: 'center', py: 4 }}>
                                            <Typography variant="body1" color="textSecondary">
                                                {t('hostDetail.noDataAvailable', 'No data available')}
                                            </Typography>
                                        </Box>
                                    )}
                                </Box>
                            );
                        }
                        return null;
                    })()}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDiagnosticDetailOpen(false)}>
                        {t('common.close', 'Close')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Ubuntu Pro Detach Confirmation Dialog */}
            <Dialog
                open={ubuntuProDetachConfirmOpen}
                onClose={handleCancelUbuntuProDetach}
                aria-labelledby="ubuntu-pro-detach-dialog-title"
                aria-describedby="ubuntu-pro-detach-dialog-description"
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle id="ubuntu-pro-detach-dialog-title">
                    {t('hostDetail.ubuntuProDetachConfirmTitle', 'Confirm Ubuntu Pro Detach')}
                </DialogTitle>
                <DialogContent>
                    <DialogContentText id="ubuntu-pro-detach-dialog-description">
                        {t('hostDetail.ubuntuProDetachConfirmMessage', 'Are you sure you want to detach Ubuntu Pro from this system? This will remove all Ubuntu Pro benefits and services for this host.')}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCancelUbuntuProDetach} color="primary">
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleConfirmUbuntuProDetach}
                        color="warning"
                        variant="contained"
                        autoFocus
                    >
                        {t('hostDetail.ubuntuProDetachConfirm', 'Detach')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Ubuntu Pro Token Dialog - only shown when no master key is configured */}
            <Dialog
                open={ubuntuProTokenDialog}
                onClose={handleUbuntuProTokenCancel}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    {t('hostDetail.ubuntuProAttachTitle', 'Attach Ubuntu Pro')}
                </DialogTitle>
                <DialogContent>
                    <Typography variant="body2" sx={{ mb: 2 }}>
                        {t('hostDetail.ubuntuProAttachDescription', 'Enter your Ubuntu Pro token to attach this system to your subscription.')}
                    </Typography>
                    <TextField
                        fullWidth
                        label={t('hostDetail.ubuntuProToken', 'Ubuntu Pro Token')}
                        value={ubuntuProToken}
                        onChange={(e) => setUbuntuProToken(e.target.value)}
                        placeholder="C1xxxxxxxxxxxxxxxxxxxxxxxxxx"
                        variant="outlined"
                        multiline={false}
                        sx={{ mt: 1 }}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleUbuntuProTokenCancel}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleUbuntuProTokenSubmit}
                        variant="contained"
                        disabled={!ubuntuProToken.trim()}
                    >
                        {t('hostDetail.ubuntuProAttachConfirm', 'Attach')}
                    </Button>
                </DialogActions>
            </Dialog>        </>
    );
};

export default HostConfirmDialogs;

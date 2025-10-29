import React, { useState, useEffect, useCallback } from 'react';
import {
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Button,
    FormControl,
    FormLabel,
    RadioGroup,
    FormControlLabel,
    Radio,
    Typography,
    Box,
    CircularProgress,
    Alert,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';
import { doCheckGraylogHealth, doAttachToGraylog, GraylogHealthResponse } from '../Services/graylog';

interface GraylogAttachmentModalProps {
    open: boolean;
    onClose: () => void;
    hostId: string;
    hostPlatform: string; // Windows, Linux, FreeBSD, etc.
}

interface MechanismOption {
    value: string;
    label: string;
    port: number;
    available: boolean;
}

const GraylogAttachmentModal: React.FC<GraylogAttachmentModalProps> = ({
    open,
    onClose,
    hostId,
    hostPlatform,
}) => {
    const { t } = useTranslation();
    const [loading, setLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [graylogServer, setGraylogServer] = useState<string>('');
    const [selectedMechanism, setSelectedMechanism] = useState<string>('');
    const [mechanisms, setMechanisms] = useState<MechanismOption[]>([]);

    const loadGraylogSettings = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const health: GraylogHealthResponse = await doCheckGraylogHealth();

            if (!health.healthy) {
                setError(t('graylog.notHealthy', 'Graylog server is not healthy or not configured'));
                setLoading(false);
                return;
            }

            // Extract server from health check or use settings
            // For now, we'll need to get this from the integration settings
            // Let's make another call to get the integration settings
            const settingsResponse = await axiosInstance.get('/api/graylog/settings');
            const settings = settingsResponse.data;

            // Determine Graylog server address
            let serverAddress = '';
            if (settings.use_managed_server && settings.host) {
                serverAddress = settings.host.ipv4 || settings.host.fqdn;
            } else if (settings.manual_url) {
                // Extract hostname/IP from URL
                const urlMatch = settings.manual_url.match(/\/\/([^:/]+)/);
                if (urlMatch) {
                    serverAddress = urlMatch[1];
                }
            }

            setGraylogServer(serverAddress);

            // Build mechanism options based on platform and available inputs
            const options: MechanismOption[] = [];

            if (hostPlatform === 'Windows') {
                // Windows only supports Sidecar
                if (health.has_windows_sidecar) {
                    options.push({
                        value: 'windows_sidecar',
                        label: t('graylog.mechanism.windowsSidecar', 'Windows Sidecar'),
                        port: health.windows_sidecar_port || 9000,
                        available: true,
                    });
                }
            } else {
                // Unix-like systems support syslog mechanisms
                if (health.has_syslog_tcp) {
                    options.push({
                        value: 'syslog_tcp',
                        label: t('graylog.mechanism.syslogTcp', 'Syslog TCP'),
                        port: health.syslog_tcp_port || 514,
                        available: true,
                    });
                }
                if (health.has_syslog_udp) {
                    options.push({
                        value: 'syslog_udp',
                        label: t('graylog.mechanism.syslogUdp', 'Syslog UDP'),
                        port: health.syslog_udp_port || 514,
                        available: true,
                    });
                }
                if (health.has_gelf_tcp) {
                    options.push({
                        value: 'gelf_tcp',
                        label: t('graylog.mechanism.gelfTcp', 'GELF TCP'),
                        port: health.gelf_tcp_port || 12201,
                        available: true,
                    });
                }
            }

            setMechanisms(options);

            // Auto-select first available option
            if (options.length > 0) {
                setSelectedMechanism(options[0].value);
            } else {
                setError(
                    t(
                        'graylog.noMechanismsAvailable',
                        'No compatible log forwarding mechanisms are available for this platform'
                    )
                );
            }
        } catch (err) {
            console.error('Error loading Graylog settings:', err);
            setError(t('graylog.errorLoadingSettings', 'Failed to load Graylog settings'));
        } finally {
            setLoading(false);
        }
    }, [t, hostPlatform]);

    useEffect(() => {
        if (open) {
            loadGraylogSettings();
        }
    }, [open, loadGraylogSettings]);

    const handleSubmit = async () => {
        if (!selectedMechanism || !graylogServer) {
            setError(t('graylog.selectMechanism', 'Please select a log forwarding mechanism'));
            return;
        }

        setSubmitting(true);
        setError(null);

        try {
            const selectedOption = mechanisms.find((m) => m.value === selectedMechanism);
            if (!selectedOption) {
                throw new Error('Selected mechanism not found');
            }

            await doAttachToGraylog(hostId, {
                mechanism: selectedMechanism,
                graylog_server: graylogServer,
                port: selectedOption.port,
            });

            // Success - close modal
            onClose();
        } catch (err) {
            console.error('Error attaching to Graylog:', err);
            const error = err as { response?: { data?: { detail?: string } } };
            setError(
                error.response?.data?.detail ||
                    t('graylog.attachError', 'Failed to attach to Graylog')
            );
        } finally {
            setSubmitting(false);
        }
    };

    const handleClose = () => {
        if (!submitting) {
            setError(null);
            setSelectedMechanism('');
            setMechanisms([]);
            onClose();
        }
    };

    return (
        <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
            <DialogTitle>
                {t('graylog.attachToGraylog', 'Attach to Graylog')}
            </DialogTitle>
            <DialogContent>
                {loading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                        <CircularProgress />
                    </Box>
                ) : error ? (
                    <Alert severity="error" sx={{ mb: 2 }}>
                        {error}
                    </Alert>
                ) : (
                    <>
                        <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                            {t('graylog.selectMechanismPrompt', 'Select the log forwarding mechanism to use:')}
                        </Typography>

                        {graylogServer && (
                            <Box sx={{ mb: 3, p: 2, bgcolor: 'background.paper', borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
                                <Typography variant="body2" color="textSecondary">
                                    {t('graylog.server', 'Graylog Server')}
                                </Typography>
                                <Typography variant="body1" sx={{ fontWeight: 'bold' }}>
                                    {graylogServer}
                                </Typography>
                            </Box>
                        )}

                        <FormControl component="fieldset" fullWidth>
                            <FormLabel component="legend">
                                {t('graylog.mechanism', 'Mechanism')}
                            </FormLabel>
                            <RadioGroup
                                value={selectedMechanism}
                                onChange={(e) => setSelectedMechanism(e.target.value)}
                            >
                                {mechanisms.map((mechanism) => (
                                    <FormControlLabel
                                        key={mechanism.value}
                                        value={mechanism.value}
                                        control={<Radio />}
                                        label={
                                            <Box>
                                                <Typography variant="body1">
                                                    {mechanism.label}
                                                </Typography>
                                                <Typography variant="caption" color="textSecondary">
                                                    {t('graylog.port', 'Port')}: {mechanism.port}
                                                </Typography>
                                            </Box>
                                        }
                                        disabled={!mechanism.available}
                                    />
                                ))}
                            </RadioGroup>
                        </FormControl>

                        {mechanisms.length === 0 && !error && (
                            <Alert severity="warning" sx={{ mt: 2 }}>
                                {t(
                                    'graylog.noMechanisms',
                                    'No log forwarding mechanisms are enabled in the Graylog configuration'
                                )}
                            </Alert>
                        )}
                    </>
                )}
            </DialogContent>
            <DialogActions>
                <Button onClick={handleClose} disabled={submitting}>
                    {t('common.cancel', 'Cancel')}
                </Button>
                <Button
                    onClick={handleSubmit}
                    variant="contained"
                    color="primary"
                    disabled={loading || submitting || !selectedMechanism || !!error}
                >
                    {submitting ? (
                        <CircularProgress size={20} color="inherit" />
                    ) : (
                        t('common.apply', 'Apply')
                    )}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default GraylogAttachmentModal;

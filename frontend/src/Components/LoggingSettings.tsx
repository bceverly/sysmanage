import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import {
    LoggingConfig,
    doGetLoggingSettings,
    doUpdateLoggingSettings,
} from '../Services/loggingSettings';

const OS_FAMILIES = ['linux', 'windows', 'macos', 'bsd'];
const OS_LABELS: Record<string, string> = {
    linux: 'Linux',
    windows: 'Windows',
    macos: 'macOS',
    bsd: 'BSD',
};


const DEFAULT_AGENT_IDENTIFIER = 'sysmanage-agent';

const emptyConfig = (identifier: string | null = null): LoggingConfig => ({
    native_enabled: false,
    native_target: 'auto',
    native_identifier: identifier,
    log_level: null,
    verbosity: null,
});

const LoggingSettings: React.FC = () => {
    const { t } = useTranslation();

    // Translated human name of each OS-native sink.  Written as literal t()
    // calls (not a dynamic key lookup) so the i18n key scanner detects every
    // key; otherwise the sink names would be flagged as orphaned.
    const sinkLabel = (family: string): string => {
        switch (family) {
            case 'linux':
                return t('logging.sinkLinux', 'the systemd journal (or syslog)');
            case 'windows':
                return t('logging.sinkWindows', 'the Windows Event Log');
            case 'macos':
                return t('logging.sinkMacos', 'syslog');
            case 'bsd':
                return t('logging.sinkBsd', 'syslog');
            default:
                return t('logging.sinkGeneric', 'the OS-native sink');
        }
    };

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(null);

    const [serverFamily, setServerFamily] = useState('linux');
    const [serverTargets, setServerTargets] = useState<string[]>(['auto', 'none']);
    const [agentTargets, setAgentTargets] = useState<Record<string, string[]>>({});

    const [server, setServer] = useState<LoggingConfig>(emptyConfig());
    const [agents, setAgents] = useState<Record<string, LoggingConfig>>({});

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const data = await doGetLoggingSettings();
            setServer({ ...emptyConfig(), ...data.server });
            setServerFamily(data.server_os_family);
            setServerTargets(data.server_valid_targets);
            setAgentTargets(data.agent_valid_targets || {});
            const nextAgents: Record<string, LoggingConfig> = {};
            OS_FAMILIES.forEach((fam) => {
                const stored = data.agents ? data.agents[fam] : null;
                const base = stored
                    ? { ...emptyConfig(), ...stored }
                    : emptyConfig();
                // Default the identifier just like the server card does.
                base.native_identifier =
                    base.native_identifier || DEFAULT_AGENT_IDENTIFIER;
                nextAgents[fam] = base;
            });
            setAgents(nextAgents);
            setError(null);
        } catch (err) {
            console.error('Error loading logging settings:', err);
            setError(t('logging.loadError', 'Failed to load logging settings'));
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load]);

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        setInfo(null);
        try {
            const payloadAgents: Record<string, LoggingConfig> = {};
            OS_FAMILIES.forEach((fam) => {
                payloadAgents[fam] = agents[fam] || emptyConfig(DEFAULT_AGENT_IDENTIFIER);
            });
            await doUpdateLoggingSettings({ server, agents: payloadAgents });
            setInfo(t('logging.saved', 'Logging settings saved and pushed to agents.'));
            await load();
        } catch (err) {
            console.error('Error saving logging settings:', err);
            setError(t('logging.saveError', 'Failed to save logging settings'));
        } finally {
            setSaving(false);
        }
    };

    const levels = useMemo(
        () => ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        [],
    );

    const renderFields = (
        cfg: LoggingConfig,
        targets: string[],
        onChange: (next: LoggingConfig) => void,
        opts: { showVerbosity: boolean; family: string },
    ) => (
        <Stack spacing={2} sx={{ mt: 1 }}>
            <FormControlLabel
                control={
                    <Switch
                        checked={cfg.native_enabled}
                        onChange={(e) =>
                            onChange({ ...cfg, native_enabled: e.target.checked })
                        }
                    />
                }
                label={t('logging.nativeEnabledSink', 'Send logs to {{sink}}', {
                    sink: sinkLabel(opts.family),
                })}
            />
            <TextField
                select
                size="small"
                fullWidth
                label={t('logging.nativeTarget', 'Native target')}
                value={cfg.native_target}
                disabled={!cfg.native_enabled}
                onChange={(e) => onChange({ ...cfg, native_target: e.target.value })}
            >
                {targets.map((tg) => (
                    <MenuItem key={tg} value={tg}>
                        {tg}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                size="small"
                fullWidth
                label={t('logging.nativeIdentifier', 'Native identifier / tag')}
                value={cfg.native_identifier ?? ''}
                disabled={!cfg.native_enabled}
                onChange={(e) =>
                    onChange({ ...cfg, native_identifier: e.target.value || null })
                }
            />
            <TextField
                select
                size="small"
                fullWidth
                label={t('logging.logLevel', 'Log level')}
                value={cfg.log_level ?? ''}
                onChange={(e) => onChange({ ...cfg, log_level: e.target.value || null })}
            >
                <MenuItem value="">
                    <em>{t('logging.levelDefault', 'Default (from yaml)')}</em>
                </MenuItem>
                {levels.map((lvl) => (
                    <MenuItem key={lvl} value={lvl}>
                        {lvl}
                    </MenuItem>
                ))}
            </TextField>
            {opts.showVerbosity && (
                <TextField
                    select
                    size="small"
                    fullWidth
                    label={t('logging.verbosity', 'Verbosity')}
                    value={cfg.verbosity ?? ''}
                    onChange={(e) =>
                        onChange({ ...cfg, verbosity: e.target.value || null })
                    }
                >
                    <MenuItem value="">
                        <em>{t('logging.levelDefault', 'Default (from yaml)')}</em>
                    </MenuItem>
                    {['low', 'medium', 'high'].map((v) => (
                        <MenuItem key={v} value={v}>
                            {v}
                        </MenuItem>
                    ))}
                </TextField>
            )}
        </Stack>
    );

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <Box sx={{ maxWidth: 1100 }}>
            <Typography variant="h6" gutterBottom>
                {t('logging.title', 'Logging')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t(
                    'logging.intro',
                    'Configure logging for the server and per-OS agent defaults. ' +
                        'These database settings override the yaml files, and changes ' +
                        'are pushed to connected agents automatically.',
                )}
            </Typography>

            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}
            {info && (
                <Alert severity="success" sx={{ mb: 2 }} onClose={() => setInfo(null)}>
                    {info}
                </Alert>
            )}

            {/* Server card — only the server OS's valid native targets are offered. */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <Typography variant="subtitle1">
                            {t('logging.serverCardTitle', 'Server logging')}
                        </Typography>
                        <Chip
                            size="small"
                            label={OS_LABELS[serverFamily] || serverFamily}
                        />
                    </Box>
                    {renderFields(server, serverTargets, setServer, {
                        showVerbosity: false,
                        family: serverFamily,
                    })}
                </CardContent>
            </Card>

            {/* Per-OS agent default cards. */}
            <Typography variant="subtitle1" gutterBottom>
                {t('logging.agentDefaultsTitle', 'Agent defaults by operating system')}
            </Typography>
            <Box
                sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                    gap: 2,
                    mb: 3,
                }}
            >
                {OS_FAMILIES.map((fam) => (
                    <Card key={fam}>
                        <CardContent>
                            <Typography variant="subtitle1" gutterBottom>
                                {OS_LABELS[fam] || fam}
                            </Typography>
                            {renderFields(
                                agents[fam] || emptyConfig(DEFAULT_AGENT_IDENTIFIER),
                                agentTargets[fam] || ['auto', 'none'],
                                (next) => setAgents({ ...agents, [fam]: next }),
                                { showVerbosity: true, family: fam },
                            )}
                        </CardContent>
                    </Card>
                ))}
            </Box>

            <Button
                variant="contained"
                onClick={handleSave}
                disabled={saving}
                startIcon={saving ? <CircularProgress size={18} /> : undefined}
            >
                {saving ? t('common.saving', 'Saving...') : t('common.save', 'Save')}
            </Button>
        </Box>
    );
};

export default LoggingSettings;

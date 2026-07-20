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
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    IconButton,
} from '@mui/material';
import ComputerIcon from '@mui/icons-material/Computer';
import InfoIcon from '@mui/icons-material/Info';
import StorageIcon from '@mui/icons-material/Storage';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import DeleteIcon from '@mui/icons-material/Delete';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import { useTranslation } from 'react-i18next';
import MaintenanceWindowCard from '../MaintenanceWindowCard';
import { hasPermissionSync, SecurityRoles } from '../../Services/permissions';
import { SysManageHost } from '../../Services/hosts';
import { OpenTelemetryStatus } from './hostDetailTypes';
import {
    formatDate,
    formatTimestamp,
    getStatusColor,
    getDisplayStatus,
    getApprovalStatusColor,
    getOpenTelemetryServiceLabel,
    getOpenTelemetryServiceColor,
} from './hostDetailHelpers';

interface HostTag {
    id: string;
    name: string;
    description: string | null;
}

interface HostInfoTabProps {
    host: SysManageHost;
    hostId: string | undefined;
    enabledShells: string[];
    licenseModules: string[];
    hostTags: HostTag[];
    availableTags: HostTag[];
    selectedTagToAdd: string;
    setSelectedTagToAdd: (value: string) => void;
    canEditTags: boolean;
    handleAddTag: () => void;
    handleRemoveTag: (tagId: string) => void;
    handleShowDialog: (title: string, content: string) => void;
    openTelemetryStatus: OpenTelemetryStatus;
    openTelemetryLoading: boolean;
    openTelemetryDeploying: boolean;
    handleDeployOpenTelemetry: () => void;
    handleOpenTelemetryStart: () => void;
    handleOpenTelemetryStop: () => void;
    handleOpenTelemetryRestart: () => void;
    handleOpenTelemetryConnect: () => void;
    handleOpenTelemetryDisconnect: () => void;
    handleRemoveOpenTelemetry: () => void;
    graylogLoading: boolean;
    graylogAttached: boolean;
    graylogMechanism: string | null;
    graylogTargetHostname: string | null;
    graylogTargetIp: string | null;
    graylogPort: number | null;
    canAttachGraylog: boolean;
    graylogEligible: boolean;
    handleAttachToGraylog: () => void;
}

const HostOpenTelemetryActions: React.FC<{
    openTelemetryStatus: NonNullable<OpenTelemetryStatus>;
    openTelemetryLoading: boolean;
    handleOpenTelemetryStart: () => void;
    handleOpenTelemetryStop: () => void;
    handleOpenTelemetryRestart: () => void;
    handleOpenTelemetryConnect: () => void;
    handleRemoveOpenTelemetry: () => void;
    handleOpenTelemetryDisconnect: () => void;
}> = ({
    openTelemetryStatus,
    openTelemetryLoading,
    handleOpenTelemetryStart,
    handleOpenTelemetryStop,
    handleOpenTelemetryRestart,
    handleOpenTelemetryConnect,
    handleRemoveOpenTelemetry,
    handleOpenTelemetryDisconnect,
}) => {
    const { t } = useTranslation();
    return (
                                                        <Grid size={{ xs: 12 }}>
                                                            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                                                                <Button
                                                                    variant="outlined"
                                                                    size="small"
                                                                    startIcon={<PlayArrowIcon />}
                                                                    onClick={handleOpenTelemetryStart}
                                                                    disabled={openTelemetryLoading}
                                                                >
                                                                    {t('hostDetail.opentelemetryStart', 'Start')}
                                                                </Button>
                                                                <Button
                                                                    variant="outlined"
                                                                    size="small"
                                                                    startIcon={<StopIcon />}
                                                                    onClick={handleOpenTelemetryStop}
                                                                    disabled={openTelemetryLoading}
                                                                >
                                                                    {t('hostDetail.opentelemetryStop', 'Stop')}
                                                                </Button>
                                                                <Button
                                                                    variant="outlined"
                                                                    size="small"
                                                                    startIcon={<RestartAltIcon />}
                                                                    onClick={handleOpenTelemetryRestart}
                                                                    disabled={openTelemetryLoading}
                                                                >
                                                                    {t('hostDetail.opentelemetryRestart', 'Restart')}
                                                                </Button>
                                                                {openTelemetryStatus.grafana_configured && !openTelemetryStatus.grafana_url && (
                                                                    <Button
                                                                        variant="outlined"
                                                                        size="small"
                                                                        onClick={handleOpenTelemetryConnect}
                                                                        disabled={openTelemetryLoading}
                                                                    >
                                                                        {t('hostDetail.opentelemetryConnect', 'Connect to Grafana')}
                                                                    </Button>
                                                                )}
                                                                <Button
                                                                    variant="outlined"
                                                                    size="small"
                                                                    onClick={handleRemoveOpenTelemetry}
                                                                    disabled={openTelemetryLoading}
                                                                >
                                                                    {t('hostDetail.opentelemetryRemove', 'Remove OpenTelemetry')}
                                                                </Button>
                                                                {openTelemetryStatus.grafana_url && (
                                                                    <Button
                                                                        variant="outlined"
                                                                        size="small"
                                                                        onClick={handleOpenTelemetryDisconnect}
                                                                        disabled={openTelemetryLoading}
                                                                    >
                                                                        {t('hostDetail.opentelemetryDisconnect', 'Disconnect from Grafana')}
                                                                    </Button>
                                                                )}
                                                            </Box>
                                                        </Grid>
    );
};

const HostOpenTelemetryCard: React.FC<{
    host: SysManageHost;
    openTelemetryStatus: OpenTelemetryStatus;
    openTelemetryLoading: boolean;
    openTelemetryDeploying: boolean;
    handleDeployOpenTelemetry: () => void;
    handleOpenTelemetryStart: () => void;
    handleOpenTelemetryStop: () => void;
    handleOpenTelemetryRestart: () => void;
    handleOpenTelemetryConnect: () => void;
    handleOpenTelemetryDisconnect: () => void;
    handleRemoveOpenTelemetry: () => void;
}> = ({
    host,
    openTelemetryStatus,
    openTelemetryLoading,
    openTelemetryDeploying,
    handleDeployOpenTelemetry,
    handleOpenTelemetryStart,
    handleOpenTelemetryStop,
    handleOpenTelemetryRestart,
    handleOpenTelemetryConnect,
    handleOpenTelemetryDisconnect,
    handleRemoveOpenTelemetry,
}) => {
    const { t } = useTranslation();
    return (
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <MedicalServicesIcon sx={{ mr: 1 }} />
                                {t('hostDetail.opentelemetryStatus', 'OpenTelemetry Status')}
                            </Typography>
                            {(() => {
                                if (openTelemetryLoading) {
                                    return (
                                        <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                                            <CircularProgress size={24} />
                                        </Box>
                                    );
                                }
                                if (openTelemetryStatus) {
                                    return (
                                        <Grid container spacing={2}>
                                            <Grid size={{ xs: 12 }}>
                                                <Typography variant="body2" color="textSecondary">
                                                    {t('hostDetail.opentelemetryDeployed', 'Deployed')}
                                                </Typography>
                                                <Typography variant="body1">
                                                    {openTelemetryStatus.deployed ? t('common.yes', 'Yes') : t('common.no', 'No')}
                                                </Typography>
                                            </Grid>
                                            {!openTelemetryStatus.deployed && hasPermissionSync(SecurityRoles.DEPLOY_OPENTELEMETRY) && host?.is_agent_privileged && (
                                                <Grid size={{ xs: 12 }}>
                                                    <Button
                                                        variant="contained"
                                                        color="primary"
                                                        size="small"
                                                        onClick={handleDeployOpenTelemetry}
                                                        disabled={openTelemetryDeploying || openTelemetryLoading}
                                                    >
                                                        {openTelemetryDeploying ? t('hostDetail.deploying', 'Deploying...') : t('hostDetail.deployOpenTelemetry', 'Deploy OpenTelemetry')}
                                                    </Button>
                                                </Grid>
                                            )}
                                            {openTelemetryStatus.deployed && (
                                                <>
                                                    <Grid size={{ xs: 12 }}>
                                                        <Typography variant="body2" color="textSecondary">
                                                            {t('hostDetail.opentelemetryServiceStatus', 'Service Status')}
                                                        </Typography>
                                                        <Chip
                                                            label={getOpenTelemetryServiceLabel(t, openTelemetryStatus.service_status)}
                                                            color={getOpenTelemetryServiceColor(openTelemetryStatus.service_status)}
                                                            size="small"
                                                        />
                                                    </Grid>
                                                    <Grid size={{ xs: 12 }}>
                                                        <Typography variant="body2" color="textSecondary">
                                                            {t('hostDetail.opentelemetryGrafanaServer', 'Grafana Server')}
                                                        </Typography>
                                                        <Typography variant="body1">
                                                            {openTelemetryStatus.grafana_url || t('hostDetail.opentelemetryNotConnected', 'Not Connected')}
                                                        </Typography>
                                                    </Grid>
                                                    {host.is_agent_privileged && (
                                                        <HostOpenTelemetryActions
                                                            openTelemetryStatus={openTelemetryStatus}
                                                            openTelemetryLoading={openTelemetryLoading}
                                                            handleOpenTelemetryStart={handleOpenTelemetryStart}
                                                            handleOpenTelemetryStop={handleOpenTelemetryStop}
                                                            handleOpenTelemetryRestart={handleOpenTelemetryRestart}
                                                            handleOpenTelemetryConnect={handleOpenTelemetryConnect}
                                                            handleRemoveOpenTelemetry={handleRemoveOpenTelemetry}
                                                            handleOpenTelemetryDisconnect={handleOpenTelemetryDisconnect}
                                                        />
                                                    )}
                                                </>
                                            )}
                                        </Grid>
                                    );
                                }
                                return (
                                    <Typography variant="body2" color="textSecondary">
                                        {t('common.notAvailable', 'Not Available')}
                                    </Typography>
                                );
                            })()}
                        </CardContent>
                    </Card>
                </Grid>
    );
};

const YesNoUnknownChip: React.FC<{
    value: boolean | null | undefined;
    yesTooltip: string;
    noTooltip: string;
}> = ({ value, yesTooltip, noTooltip }) => {
    const { t } = useTranslation();
    if (value === undefined || value === null) {
        return (
            <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
                {t('common.unknown', 'Unknown')}
            </Typography>
        );
    }
    return (
        <Chip
            label={value ? t('common.yes') : t('common.no')}
            color={value ? 'success' : 'error'}
            size="small"
            variant="filled"
            title={value ? yesTooltip : noTooltip}
        />
    );
};

const HostBasicInfoCard: React.FC<{
    host: SysManageHost;
    enabledShells: string[];
}> = ({
    host,
    enabledShells,
}) => {
    const { t } = useTranslation();
    return (
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <InfoIcon sx={{ mr: 1 }} />
                                {t('hostDetail.basicInfo', 'Basic Information')}
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.fqdn', 'FQDN')}
                                    </Typography>
                                    <Typography variant="body1">{host.fqdn}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.ipv4', 'IPv4')}
                                    </Typography>
                                    <Typography variant="body1">{host.ipv4 || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.ipv6', 'IPv6')}
                                    </Typography>
                                    <Typography variant="body1">{host.ipv6 || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.publicIp', 'Public IP')}
                                    </Typography>
                                    <Typography variant="body1">{host.public_ip || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.geoLocation', 'Geographic Location')}
                                    </Typography>
                                    <Typography variant="body1">
                                        {host.geo_city || host.geo_country_code
                                            ? [
                                                host.geo_city,
                                                host.geo_subdivision_code,
                                                host.geo_country_code,
                                              ]
                                                  .filter(Boolean)
                                                  .join(', ')
                                            : t('common.notAvailable')}
                                    </Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.status', 'Status')}
                                    </Typography>
                                    <Chip
                                        label={getDisplayStatus(host) === 'up' ? t('hosts.up') : t('hosts.down')}
                                        color={getStatusColor(getDisplayStatus(host))}
                                        size="small"
                                    />
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.approvalStatus', 'Approval Status')}
                                    </Typography>
                                    <Chip
                                        label={host.approval_status.charAt(0).toUpperCase() + host.approval_status.slice(1)}
                                        color={getApprovalStatusColor(host.approval_status)}
                                        size="small"
                                    />
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.lastCheckin', 'Last Check-in')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(t, host.last_access)}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.scriptsEnabled', 'Scripts Enabled')}
                                    </Typography>
                                    <YesNoUnknownChip
                                        value={host.script_execution_enabled}
                                        yesTooltip={t('hosts.scriptsEnabledTooltip')}
                                        noTooltip={t('hosts.scriptsDisabledTooltip')}
                                    />
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.privileged', 'Privileged')}
                                    </Typography>
                                    <YesNoUnknownChip
                                        value={host.is_agent_privileged}
                                        yesTooltip={t('hosts.runningPrivileged')}
                                        noTooltip={t('hosts.runningUnprivileged')}
                                    />
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.active', 'Active')}
                                    </Typography>
                                    <Chip
                                        label={host.active ? t('common.yes') : t('common.no')}
                                        color={host.active ? 'success' : 'default'}
                                        size="small"
                                    />
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.shellsAllowed', 'Shells Allowed')}
                                    </Typography>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                                        {/* Enabled Shells */}
                                        {enabledShells.length > 0 ? enabledShells.map((shell: string) => (
                                            <Chip
                                                key={shell}
                                                label={shell}
                                                color="success"
                                                size="small"
                                                variant="filled"
                                            />
                                        )) : (
                                            <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
                                                {t('common.none', 'None')}
                                            </Typography>
                                        )}
                                    </Box>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.agentVersion', 'Agent Version')}
                                    </Typography>
                                    <Typography variant="body1">{host.agent_version || t('common.notAvailable', 'N/A')}</Typography>
                                </Grid>
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>
    );
};

const HostOsInfoCard: React.FC<{
    host: SysManageHost;
    handleShowDialog: (title: string, content: string) => void;
}> = ({
    host,
    handleShowDialog,
}) => {
    const { t } = useTranslation();
    return (
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <ComputerIcon sx={{ mr: 1 }} />
                                {t('hostDetail.osInfo', 'Operating System')}
                                <Typography variant="caption" color="textSecondary">
                                    {t('hosts.updated', 'Updated')}: {formatTimestamp(t, host.os_version_updated_at)}
                                </Typography>
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid size={{ xs: 12 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.platform', 'Platform')}
                                    </Typography>
                                    <Typography variant="body1">{host.platform || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.platformRelease', 'Platform Release')}
                                    </Typography>
                                    <Typography variant="body1">{host.platform_release || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.kernel', 'Kernel')}
                                    </Typography>
                                    <Typography variant="body1" sx={{ wordBreak: 'break-word' }}>
                                        {host.platform_version || t('common.notAvailable')}
                                    </Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.architecture', 'Architecture')}
                                    </Typography>
                                    <Typography variant="body1">{host.machine_architecture || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.processor', 'Processor')}
                                    </Typography>
                                    <Typography variant="body1">{host.processor || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.timezone', 'Timezone')}
                                    </Typography>
                                    <Typography variant="body1">{host.timezone || t('common.notAvailable')}</Typography>
                                </Grid>
                                {host.os_details && (
                                    <Grid size={{ xs: 12 }}>
                                        <Typography variant="body2" color="textSecondary" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                            {t('hostDetail.osDetails', 'Additional Details')}
                                            <IconButton
                                                size="small"
                                                onClick={() => handleShowDialog(t('hostDetail.additionalOSDetails', 'Additional OS Details'), host.os_details || '')}
                                                sx={{ color: 'textSecondary' }}
                                            >
                                                <HelpOutlineIcon fontSize="small" />
                                            </IconButton>
                                        </Typography>
                                    </Grid>
                                )}
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>
    );
};

const HostGraylogCard: React.FC<{
    graylogLoading: boolean;
    graylogAttached: boolean;
    graylogMechanism: string | null;
    graylogTargetHostname: string | null;
    graylogTargetIp: string | null;
    graylogPort: number | null;
    canAttachGraylog: boolean;
    graylogEligible: boolean;
    handleAttachToGraylog: () => void;
}> = ({
    graylogLoading,
    graylogAttached,
    graylogMechanism,
    graylogTargetHostname,
    graylogTargetIp,
    graylogPort,
    canAttachGraylog,
    graylogEligible,
    handleAttachToGraylog,
}) => {
    const { t } = useTranslation();
    return (
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <StorageIcon sx={{ mr: 1 }} />
                                {t('hostDetail.graylogStatus', 'Graylog Status')}
                            </Typography>
                            {graylogLoading ? (
                                <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                                    <CircularProgress size={24} />
                                </Box>
                            ) : (
                                <Grid container spacing={2}>
                                    <Grid size={{ xs: 12 }}>
                                        <Typography variant="body2" color="textSecondary">
                                            {t('hostDetail.graylogAttached', 'Attached to Graylog')}
                                        </Typography>
                                        <Typography variant="body1">
                                            {graylogAttached ? t('common.yes', 'Yes') : t('common.no', 'No')}
                                        </Typography>
                                    </Grid>
                                    {graylogAttached && (
                                        <>
                                            {graylogMechanism && (
                                                <Grid size={{ xs: 12 }}>
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.graylogMechanism', 'Mechanism')}
                                                    </Typography>
                                                    <Typography variant="body1">
                                                        {graylogMechanism === 'syslog_tcp' && t('graylog.mechanism.syslogTcp', 'Syslog TCP')}
                                                        {graylogMechanism === 'syslog_udp' && t('graylog.mechanism.syslogUdp', 'Syslog UDP')}
                                                        {graylogMechanism === 'gelf_tcp' && t('graylog.mechanism.gelfTcp', 'GELF TCP')}
                                                        {graylogMechanism === 'windows_sidecar' && t('graylog.mechanism.windowsSidecar', 'Windows Sidecar')}
                                                        {graylogPort && ` ${t('hostDetail.graylogPort', '(port {{port}})', { port: graylogPort })}`}
                                                    </Typography>
                                                </Grid>
                                            )}
                                            {(graylogTargetHostname || graylogTargetIp) && (
                                                <Grid size={{ xs: 12 }}>
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.graylogTarget', 'Target')}
                                                    </Typography>
                                                    <Typography variant="body1">
                                                        {graylogTargetHostname || graylogTargetIp}
                                                    </Typography>
                                                </Grid>
                                            )}
                                        </>
                                    )}
                                    {!graylogAttached && canAttachGraylog && graylogEligible && (
                                        <Grid size={{ xs: 12 }}>
                                            <Button
                                                variant="contained"
                                                color="primary"
                                                size="small"
                                                onClick={handleAttachToGraylog}
                                                disabled={graylogLoading}
                                            >
                                                {t('hostDetail.attachToGraylog', 'Attach To Graylog')}
                                            </Button>
                                        </Grid>
                                    )}
                                    {!canAttachGraylog && (
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.graylogNotConfigured', 'Graylog integration not configured or not healthy')}
                                            </Typography>
                                        </Grid>
                                    )}
                                    {canAttachGraylog && !graylogEligible && (
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.graylogRequiresPrivileged', 'Requires agent in privileged mode')}
                                            </Typography>
                                        </Grid>
                                    )}
                                </Grid>
                            )}
                        </CardContent>
                    </Card>
                </Grid>
    );
};

const HostInfoTab: React.FC<HostInfoTabProps> = ({
    host,
    hostId,
    enabledShells,
    licenseModules,
    hostTags,
    availableTags,
    selectedTagToAdd,
    setSelectedTagToAdd,
    canEditTags,
    handleAddTag,
    handleRemoveTag,
    handleShowDialog,
    openTelemetryStatus,
    openTelemetryLoading,
    openTelemetryDeploying,
    handleDeployOpenTelemetry,
    handleOpenTelemetryStart,
    handleOpenTelemetryStop,
    handleOpenTelemetryRestart,
    handleOpenTelemetryConnect,
    handleOpenTelemetryDisconnect,
    handleRemoveOpenTelemetry,
    graylogLoading,
    graylogAttached,
    graylogMechanism,
    graylogTargetHostname,
    graylogTargetIp,
    graylogPort,
    canAttachGraylog,
    graylogEligible,
    handleAttachToGraylog,
}) => {
    const { t } = useTranslation();
    return (
                <Grid container spacing={3}>
                {/* Maintenance window status (Phase 14.2) */}
                <Grid size={{ xs: 12, md: 6 }}>
                    <MaintenanceWindowCard hostId={hostId || ''} />
                </Grid>
                {/* Basic Information */}
                <HostBasicInfoCard host={host} enabledShells={enabledShells} />

                {/* Operating System Information */}
                <HostOsInfoCard host={host} handleShowDialog={handleShowDialog} />

                {/* OpenTelemetry Status — Pro+ feature gated on observability_engine */}
                {licenseModules.includes('observability_engine') && (
                    <HostOpenTelemetryCard
                        host={host}
                        openTelemetryStatus={openTelemetryStatus}
                        openTelemetryLoading={openTelemetryLoading}
                        openTelemetryDeploying={openTelemetryDeploying}
                        handleDeployOpenTelemetry={handleDeployOpenTelemetry}
                        handleOpenTelemetryStart={handleOpenTelemetryStart}
                        handleOpenTelemetryStop={handleOpenTelemetryStop}
                        handleOpenTelemetryRestart={handleOpenTelemetryRestart}
                        handleOpenTelemetryConnect={handleOpenTelemetryConnect}
                        handleOpenTelemetryDisconnect={handleOpenTelemetryDisconnect}
                        handleRemoveOpenTelemetry={handleRemoveOpenTelemetry}
                    />
                )}

                {/* Graylog Status — Pro+ feature gated on observability_engine */}
                {licenseModules.includes('observability_engine') && (
                    <HostGraylogCard
                        graylogLoading={graylogLoading}
                        graylogAttached={graylogAttached}
                        graylogMechanism={graylogMechanism}
                        graylogTargetHostname={graylogTargetHostname}
                        graylogTargetIp={graylogTargetIp}
                        graylogPort={graylogPort}
                        canAttachGraylog={canAttachGraylog}
                        graylogEligible={graylogEligible}
                        handleAttachToGraylog={handleAttachToGraylog}
                    />
                )}

                {/* Tags */}
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <LocalOfferIcon sx={{ mr: 1 }} />
                                {t('hostDetail.tags', 'Tags')}
                            </Typography>
                            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                                {hostTags.map(tag => (
                                    <Chip
                                        key={tag.id}
                                        label={tag.name}
                                        onDelete={canEditTags ? () => handleRemoveTag(tag.id) : undefined}
                                        deleteIcon={canEditTags ? <DeleteIcon /> : undefined}
                                        variant="outlined"
                                    />
                                ))}
                                {hostTags.length === 0 && (
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.noTags', 'No tags assigned')}
                                    </Typography>
                                )}
                            </Box>
                            {canEditTags && (
                                <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                                    <FormControl size="small" sx={{ minWidth: 200 }}>
                                        <InputLabel>{t('hostDetail.addTag', 'Add Tag')}</InputLabel>
                                        <Select
                                            value={selectedTagToAdd}
                                            onChange={(e) => setSelectedTagToAdd(e.target.value)}
                                            label={t('hostDetail.addTag', 'Add Tag')}
                                        >
                                            {availableTags.map(tag => (
                                                <MenuItem key={tag.id} value={tag.id}>
                                                    {tag.name}
                                                </MenuItem>
                                            ))}
                                        </Select>
                                    </FormControl>
                                    <Button
                                        variant="contained"
                                        onClick={handleAddTag}
                                        disabled={!selectedTagToAdd}
                                        size="small"
                                    >
                                        {t('common.add', 'Add')}
                                    </Button>
                                </Box>
                            )}
                        </CardContent>
                    </Card>
                </Grid>
                </Grid>
    );
};

export default HostInfoTab;

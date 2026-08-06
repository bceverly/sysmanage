// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import {
    Box,
    Divider,
    FormControl,
    FormControlLabel,
    InputLabel,
    MenuItem,
    Select,
    Switch,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { ChildHostFormData, WINDOWS_EDITIONS } from './hostDetailTypes';

interface WindowsChildHostFieldsProps {
    formData: ChildHostFormData;
    setFormData: React.Dispatch<React.SetStateAction<ChildHostFormData>>;
    disabled: boolean;
    validated: boolean;
}

/**
 * The Windows Server section of the Create Child Host dialog (Phase 12.5).
 *
 * Split out of CreateChildHostDialog rather than inlined: the Windows path
 * roughly doubles the field count, and the dialog already branches four ways
 * on childType.  Keeping it here also means the section can be tested without
 * standing up the whole dialog.
 *
 * There is deliberately no "version" picker — the version IS the distribution
 * (Windows Server 2022 / 2025 are separate catalog entries), so a second
 * control would be a way for the two to disagree.
 */
const WindowsChildHostFields: React.FC<WindowsChildHostFieldsProps> = ({
    formData,
    setFormData,
    disabled,
    validated,
}) => {
    const { t } = useTranslation();
    const joinDomain = Boolean(formData.windowsJoinDomain);
    const isoMissing = validated && !formData.windowsIsoPath;

    return (
        <Box sx={{ mb: 1 }}>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" sx={{ mb: 2 }}>
                {t('hostDetail.windowsSectionTitle', 'Windows Server setup')}
            </Typography>

            <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel id="windows-edition-label">
                    {t('hostDetail.windowsEditionLabel', 'Edition')}
                </InputLabel>
                <Select
                    labelId="windows-edition-label"
                    value={formData.windowsEdition}
                    label={t('hostDetail.windowsEditionLabel', 'Edition')}
                    onChange={(e) => setFormData({ ...formData, windowsEdition: e.target.value })}
                    disabled={disabled}
                >
                    {WINDOWS_EDITIONS.map((edition) => (
                        <MenuItem key={edition.value} value={edition.value}>
                            {t(edition.labelKey, edition.label)}
                        </MenuItem>
                    ))}
                </Select>
            </FormControl>

            {/* Required: Microsoft publishes no stable unauthenticated URL for
                Server media, so unlike the Linux guests there is nothing to
                download and the operator must stage the ISO on the parent. */}
            <TextField
                fullWidth
                required
                label={t('hostDetail.windowsIsoPathLabel', 'Windows ISO path on the parent host')}
                value={formData.windowsIsoPath}
                onChange={(e) => setFormData({ ...formData, windowsIsoPath: e.target.value })}
                disabled={disabled}
                error={isoMissing}
                sx={{ mb: 2 }}
                helperText={
                    isoMissing
                        ? t('hostDetail.windowsIsoPathRequired', 'Please enter the path to the Windows installation ISO')
                        : t('hostDetail.windowsIsoPathHelp', 'Absolute path on the parent, e.g. /var/lib/libvirt/images/iso/server2022.iso')
                }
            />

            {/* Secret-typed: the key is stored in OpenBAO, never in the
                database, and is never returned by the API once submitted. */}
            <TextField
                fullWidth
                type="password"
                label={t('hostDetail.windowsProductKeyLabel', 'License key')}
                value={formData.windowsProductKey}
                onChange={(e) => setFormData({ ...formData, windowsProductKey: e.target.value })}
                disabled={disabled}
                sx={{ mb: 2 }}
                helperText={t(
                    'hostDetail.windowsProductKeyHelp',
                    'AVMA, MAK or KMS key. Leave blank for evaluation media, which installs without one. Stored in OpenBAO, never in the database.',
                )}
            />

            <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <TextField
                    fullWidth
                    label={t('hostDetail.windowsTimezoneLabel', 'Time zone')}
                    value={formData.windowsTimezone}
                    onChange={(e) => setFormData({ ...formData, windowsTimezone: e.target.value })}
                    disabled={disabled}
                    helperText={t('hostDetail.windowsTimezoneHelp', 'Windows time-zone ID, e.g. "UTC"')}
                />
                <TextField
                    fullWidth
                    label={t('hostDetail.windowsLocaleLabel', 'Locale')}
                    value={formData.windowsLocale}
                    onChange={(e) => setFormData({ ...formData, windowsLocale: e.target.value })}
                    disabled={disabled}
                    helperText={t('hostDetail.windowsLocaleHelp', 'UI and input locale, e.g. "en-US"')}
                />
            </Box>

            <FormControlLabel
                control={
                    <Switch
                        checked={joinDomain}
                        onChange={(e) =>
                            setFormData({
                                ...formData,
                                // Clearing the domain is what turns the join OFF
                                // everywhere else (backend and engine both treat
                                // an empty domain as "workgroup"), so the toggle
                                // clears the whole group rather than leaving
                                // orphaned credentials behind.
                                windowsJoinDomain: e.target.checked ? formData.windowsJoinDomain : '',
                                windowsDomainOu: e.target.checked ? formData.windowsDomainOu : '',
                                windowsDomainUser: e.target.checked ? formData.windowsDomainUser : '',
                                windowsDomainPassword: e.target.checked ? formData.windowsDomainPassword : '',
                            })
                        }
                        disabled={disabled}
                    />
                }
                label={t('hostDetail.windowsJoinDomainToggle', 'Join an Active Directory domain')}
                sx={{ mb: 1 }}
            />

            {joinDomain && (
                <Box sx={{ pl: 2, borderLeft: '2px solid', borderColor: 'divider' }}>
                    <TextField
                        fullWidth
                        required
                        label={t('hostDetail.windowsDomainLabel', 'Domain')}
                        value={formData.windowsJoinDomain}
                        onChange={(e) => setFormData({ ...formData, windowsJoinDomain: e.target.value })}
                        disabled={disabled}
                        sx={{ mb: 2 }}
                        helperText={t('hostDetail.windowsDomainHelp', 'e.g. corp.example.com')}
                    />
                    <TextField
                        fullWidth
                        label={t('hostDetail.windowsDomainOuLabel', 'Computer account OU (optional)')}
                        value={formData.windowsDomainOu}
                        onChange={(e) => setFormData({ ...formData, windowsDomainOu: e.target.value })}
                        disabled={disabled}
                        sx={{ mb: 2 }}
                        helperText={t('hostDetail.windowsDomainOuHelp', 'e.g. OU=Servers,DC=corp,DC=example,DC=com')}
                    />
                    <TextField
                        fullWidth
                        required
                        label={t('hostDetail.windowsDomainUserLabel', 'Join account')}
                        value={formData.windowsDomainUser}
                        onChange={(e) => setFormData({ ...formData, windowsDomainUser: e.target.value })}
                        disabled={disabled}
                        sx={{ mb: 2 }}
                        helperText={t('hostDetail.windowsDomainUserHelp', 'An account permitted to join machines to the domain')}
                    />
                    <TextField
                        fullWidth
                        required
                        type="password"
                        label={t('hostDetail.windowsDomainPasswordLabel', 'Join account password')}
                        value={formData.windowsDomainPassword}
                        onChange={(e) => setFormData({ ...formData, windowsDomainPassword: e.target.value })}
                        disabled={disabled}
                        sx={{ mb: 2 }}
                    />
                </Box>
            )}

            <Divider sx={{ my: 2 }} />
        </Box>
    );
};

export default WindowsChildHostFields;

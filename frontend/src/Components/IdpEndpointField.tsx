// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A SysManage address that has to be registered, exactly, with the identity
// provider (OIDC redirect URI, SAML ACS URL / entity ID / metadata URL).  The
// server fills it in when left blank -- it contains the provider's own id,
// unknown until the first save -- so the field is optional and offers a copy
// button once there is a value to copy (2026-10-07: an admin had to find the
// provider id in the database to complete an Entra ID setup).

import React, { useState } from 'react';
import { IconButton, InputAdornment, TextField, Tooltip } from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import { useTranslation } from 'react-i18next';

interface IdpEndpointFieldProps {
    label: string;
    helperText: string;
    value: string;
    /** Omit for a read-only address (e.g. the SAML metadata URL). */
    onChange?: (value: string) => void;
}

const IdpEndpointField: React.FC<IdpEndpointFieldProps> = ({ label, helperText, value, onChange }) => {
    const { t } = useTranslation();
    const [copied, setCopied] = useState(false);

    const copy = () => {
        void globalThis.navigator.clipboard?.writeText(value).then(() => {
            setCopied(true);
            globalThis.setTimeout(() => setCopied(false), 1500);
        });
    };

    return (
        <TextField
            label={label}
            helperText={helperText}
            value={value}
            onChange={onChange ? (e) => onChange(e.target.value) : undefined}
            fullWidth
            slotProps={{
                input: {
                    readOnly: !onChange,
                    endAdornment: value ? (
                        <InputAdornment position="end">
                            <Tooltip title={copied ? t('common.copied', 'Copied') : t('common.copy', 'Copy')}>
                                <IconButton
                                    edge="end"
                                    aria-label={t('common.copy', 'Copy')}
                                    onClick={copy}
                                >
                                    <ContentCopyIcon fontSize="small" />
                                </IconButton>
                            </Tooltip>
                        </InputAdornment>
                    ) : undefined,
                },
            }}
        />
    );
};

export default IdpEndpointField;

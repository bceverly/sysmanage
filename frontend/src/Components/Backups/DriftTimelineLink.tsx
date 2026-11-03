// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A link to a host's drift timeline (Pro+ backup_engine, 24.7) from
// configuration drift (20.3) and the host's software history: what changed
// between its backups, optionally narrowed to one path.  Nothing without the
// engine.  A plain link, so it works from any page, routed or not.

import React from 'react';
import { Button } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useModuleLicensed } from '../../hooks/useModuleLicensed';

export const driftTimelineHref = (hostId: string, path?: string | null): string =>
    `/hosts/${hostId}${path ? `?driftPath=${encodeURIComponent(path)}` : ''}#backup`;

const DriftTimelineLink: React.FC<{ hostId: string; path?: string | null }> = ({ hostId, path }) => {
    const { t } = useTranslation();
    const licensed = useModuleLicensed('backup_engine');
    if (!licensed) return null;
    return (
        <Button size="small" href={driftTimelineHref(hostId, path)}>
            {t('backups.drift.link', 'What changed between backups')}
        </Button>
    );
};

export default DriftTimelineLink;

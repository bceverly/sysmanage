// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// What a restore (or its preview) says beyond its counts, from restate after
// 2.2.0.14: the paths that matched nothing in the snapshot (which leave the
// restore Incomplete), the paths reached through the snapshot's own symbolic
// links (a snap's /var/snap/<name>/current), and the hooks that put right
// what pausing a service left in the files.  An older restate reports none
// of these, and nothing is shown.

import React from 'react';
import { Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { BackupRun } from '../../Services/backups';

export interface RestoreNote {
    text: string;
    /** A path left out or a hook that failed: why the restore is Incomplete. */
    warning: boolean;
}

interface Resolved { include?: unknown; path?: unknown }
interface Hook { dump_dir?: unknown; kind?: unknown; name?: unknown; status?: unknown }

const text = (value: unknown): string => (typeof value === 'string' ? value : '');
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

/** restate 2.2 nests a restore's fields under ``restore``. */
const restoreOf = (run: BackupRun): Record<string, unknown> => {
    const raw = run.result ?? {};
    const nested = raw.restore;
    return nested && typeof nested === 'object' ? (nested as Record<string, unknown>) : raw;
};

/** The service a hook is for: its kind and name, or (a preview reads no
 *  marker) the dump directory's own name, <kind>-<name>. */
const hookService = (hook: Hook): string => {
    const kind = text(hook.kind);
    const name = text(hook.name);
    if (kind) return name && name !== kind ? `${kind} ${name}` : kind;
    const base = text(hook.dump_dir).split('/').findLast(Boolean) ?? '';
    const half = (base.length - 1) / 2;
    // nextcloud-nextcloud: a snap's kind and name are one word.
    return base[half] === '-' && base.slice(0, half) === base.slice(half + 1) ? base.slice(0, half) : base;
};

const hookNote = (t: TFunction, hook: Hook): RestoreNote | null => {
    const service = hookService(hook);
    const dir = text(hook.dump_dir);
    switch (hook.status) {
        case 'would_run':
            return { warning: false, text: t('backups.restore.hookWillRun',
                'After the restore, restate will run the {{service}} hook to put right what pausing it left in the restored files.',
                { service }) };
        case 'ran':
            return { warning: false, text: t('backups.restore.hookRan',
                'The {{service}} hook put right what pausing it left in the restored files.', { service }) };
        case 'unknown':
            return { warning: false, text: t('backups.restore.hookNothing',
                'The {{service}} hook had nothing to put right.', { service }) };
        case 'failed':
            return { warning: true, text: t('backups.restore.hookFailed',
                'The {{service}} hook failed after the restore, so the restore is incomplete. The restate log on the host says why.',
                { service }) };
        case 'no_hook':
            return { warning: true, text: t('backups.restore.hookMissing',
                'This host has no {{service}} hook to put right what pausing it left in the restored files. Do that by hand.',
                { service }) };
        case 'unreadable':
            return { warning: true, text: t('backups.restore.hookUnreadable',
                'restate could not tell which hook {{dir}} is for, so no hook was run.', { dir }) };
        default:
            return null;
    }
};

/** Every note, warnings first. */
export const restoreNotes = (t: TFunction, run: BackupRun): RestoreNote[] => {
    const restore = restoreOf(run);
    const notes: RestoreNote[] = [];
    const unmatched = list(restore.unmatched).map(text).filter(Boolean);
    if (unmatched.length) {
        notes.push({ warning: true, text: t('backups.restore.unmatched',
            '{{n}} of your paths matched nothing in the snapshot: {{paths}}',
            { n: unmatched.length, paths: unmatched.join(', ') }) });
    }
    for (const entry of list(restore.resolved) as Resolved[]) {
        if (!text(entry?.include) || !text(entry?.path)) continue;
        notes.push({ warning: false, text: t('backups.restore.resolved',
            '{{include}} was followed to {{path}} through the snapshot\'s symbolic links.',
            { include: text(entry.include), path: text(entry.path) }) });
    }
    for (const hook of list(restore.hooks) as Hook[]) {
        const note = hook && typeof hook === 'object' ? hookNote(t, hook) : null;
        if (note) notes.push(note);
    }
    return [...notes.filter(n => n.warning), ...notes.filter(n => !n.warning)];
};

/** The notes, one line each; ``warningsOnly`` for the job list. */
export const RestoreNotes: React.FC<{ run: BackupRun; warningsOnly?: boolean }> = ({ run, warningsOnly = false }) => {
    const { t } = useTranslation();
    const notes = restoreNotes(t, run).filter(n => n.warning || !warningsOnly);
    return (
        <>
            {notes.map(note => (
                <Typography key={note.text} variant={warningsOnly ? 'caption' : 'body2'} display="block"
                    color={note.warning ? 'warning.main' : 'text.secondary'}>
                    {note.text}
                </Typography>
            ))}
        </>
    );
};

export default RestoreNotes;

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import AddIcon from '@mui/icons-material/Add';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import SelectionActionBar, { SelectionAction } from './SelectionActionBar';

interface ThirdPartyReposActionBarProps {
    selectionCount: number;
    onClearSelection: () => void;
    privilegedMode: boolean;
    loading: boolean;
    canAdd: boolean;
    canEnable: boolean;
    canDisable: boolean;
    canDelete: boolean;
    onAdd: () => void;
    onEnable: () => void;
    onDisable: () => void;
    onDelete: () => void;
}

/**
 * Action bar for the third-party repositories grid.
 *
 * Extracted from the page rather than inlined: ThirdPartyRepositories.tsx sits
 * against the 1000-line gate, and the bar is the same shape as HostsActionBar
 * so it belongs beside it.
 */
const ThirdPartyReposActionBar: React.FC<ThirdPartyReposActionBarProps> = ({
    selectionCount,
    onClearSelection,
    privilegedMode,
    loading,
    canAdd,
    canEnable,
    canDisable,
    canDelete,
    onAdd,
    onEnable,
    onDisable,
    onDelete,
}) => {
    const { t } = useTranslation();
    const none = selectionCount === 0;

    // Every action is gated the same two ways, so the explanation is derived
    // once instead of being repeated four times.  Privilege is reported ahead
    // of selection because it is the condition the operator cannot fix by
    // clicking a row.
    const reason = (needsSelection: boolean) => {
        if (!privilegedMode) {
            return t(
                'thirdPartyRepos.requiresPrivileged',
                'The host must be running in privileged mode',
            );
        }
        return needsSelection && none
            ? t('common.requiresSelection', 'Select at least one row')
            : undefined;
    };

    const count = { count: selectionCount };
    const actions: SelectionAction[] = [
        {
            id: 'add',
            label: t('thirdPartyRepos.addRepository'),
            icon: <AddIcon />,
            primary: true,
            disabled: !canAdd || !privilegedMode || loading,
            disabledReason: reason(false),
            onClick: onAdd,
        },
        {
            id: 'enable',
            label: t('thirdPartyRepos.enableSelected', 'Enable Selected ({{count}})', count),
            icon: <CheckCircleIcon />,
            color: 'success',
            primary: true,
            disabled: !canEnable || !privilegedMode || none || loading,
            disabledReason: reason(true),
            onClick: onEnable,
        },
        {
            id: 'disable',
            label: t('thirdPartyRepos.disableSelected', 'Disable Selected ({{count}})', count),
            icon: <CancelIcon />,
            color: 'warning',
            primary: true,
            disabled: !canDisable || !privilegedMode || none || loading,
            disabledReason: reason(true),
            onClick: onDisable,
        },
        {
            id: 'delete',
            label: t('thirdPartyRepos.deleteSelected', 'Delete Selected ({{count}})', count),
            icon: <DeleteIcon />,
            destructive: true,
            disabled: !canDelete || !privilegedMode || none || loading,
            disabledReason: reason(true),
            onClick: onDelete,
        },
    ];

    return (
        <SelectionActionBar
            actions={actions}
            selectionCount={selectionCount}
            onClearSelection={onClearSelection}
            sx={{ flexShrink: 0 }}
        />
    );
};

export default ThirdPartyReposActionBar;

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { Box, Typography, List, ListItemButton, ListItemText } from '@mui/material';
import { navRailContainerSx, navRailGroupSx, navRailGroupTitleSx, navRailItemSx } from '../navRailStyles';

interface NavTab { id: string; label: string; }
interface NavGroup { id: string; label: string; tabs: NavTab[]; }
interface TabDef { id: string; }

interface HostDetailNavRailProps {
    hostTabGroups: NavGroup[];
    tabDefinitions: TabDef[];
    currentTab: number;
    handleTabChange: (event: React.SyntheticEvent, newValue: number) => void;
}

const HostDetailNavRail: React.FC<HostDetailNavRailProps> = ({
    hostTabGroups,
    tabDefinitions,
    currentTab,
    handleTabChange,
}) => {
    return (
        <Box sx={navRailContainerSx}>
            {hostTabGroups.map(group => (
                <Box key={group.id} sx={navRailGroupSx}>
                    <Typography variant="overline" sx={navRailGroupTitleSx}>
                        {group.label}
                    </Typography>
                    <List dense disablePadding>
                        {group.tabs.map(tab => {
                            const idx = tabDefinitions.findIndex(td => td.id === tab.id);
                            return (
                                <ListItemButton
                                    key={tab.id}
                                    selected={currentTab === idx}
                                    onClick={(e) => handleTabChange(e, idx)}
                                    sx={navRailItemSx}
                                >
                                    <ListItemText
                                        primary={tab.label}
                                        slotProps={{ primary: { variant: 'body2' } }}
                                    />
                                </ListItemButton>
                            );
                        })}
                    </List>
                </Box>
            ))}
        </Box>
    );
};

export default HostDetailNavRail;

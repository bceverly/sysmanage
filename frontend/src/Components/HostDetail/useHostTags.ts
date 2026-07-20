// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Host tag state, loaders and add/remove handlers for the Host Detail page.

import React, { useCallback, useEffect, useState } from 'react';
import type { TFunction } from 'i18next';
import axiosInstance from '../../Services/api';
import type { SnackbarSeverity } from './useHostSnackbar';

interface HostTag {
    id: string;
    name: string;
    description: string | null;
}

interface UseHostTagsArgs {
    hostId: string | undefined;
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useHostTags = ({
    hostId,
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
}: UseHostTagsArgs) => {
    const [hostTags, setHostTags] = useState<HostTag[]>([]);
    const [availableTags, setAvailableTags] = useState<HostTag[]>([]);
    const [selectedTagToAdd, setSelectedTagToAdd] = useState<string>('');

    const loadHostTags = useCallback(async () => {
        if (!hostId) return;

        try {
            const response = await axiosInstance.get(`/api/v1/hosts/${hostId}/tags`);

            if (response.status === 200) {
                const tags = response.data;
                setHostTags(tags);
            }
        } catch (error) {
            console.error('Error loading host tags:', error);
        }
    }, [hostId]);

    const loadAvailableTags = useCallback(async () => {
        try {
            const response = await axiosInstance.get('/api/v1/tags');

            if (response.status === 200) {
                const allTags = response.data;
                // Filter out tags that are already assigned to this host
                const available = allTags.filter((tag: HostTag) =>
                    !hostTags.some(hostTag => hostTag.id === tag.id)
                );
                setAvailableTags(available);
            }
        } catch (error) {
            console.error('Error loading available tags:', error);
        }
    }, [hostTags]);

    // Load tags when component mounts and when hostTags change
    useEffect(() => {
        if (hostId) {
            loadHostTags();
        }
    }, [hostId, loadHostTags]);

    useEffect(() => {
        loadAvailableTags();
    }, [hostTags, loadAvailableTags]);

    const handleAddTag = async () => {
        if (!hostId || !selectedTagToAdd) return;

        try {
            const response = await globalThis.fetch(`/api/v1/hosts/${hostId}/tags/${selectedTagToAdd}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
                },
            });

            if (response.ok) {
                await loadHostTags();
                await loadAvailableTags();
                setSelectedTagToAdd('');
                setSnackbarMessage(t('hostDetail.tagAdded', 'Tag added successfully'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                setSnackbarMessage(t('hostDetail.tagAddFailed', 'Failed to add tag'));
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
            }
        } catch (error) {
            console.error('Error adding tag:', error);
            setSnackbarMessage(t('hostDetail.tagAddFailed', 'Failed to add tag'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleRemoveTag = async (tagId: string) => {
        if (!hostId) return;

        try {
            const response = await globalThis.fetch(`/api/v1/hosts/${hostId}/tags/${tagId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
                },
            });

            if (response.ok) {
                await loadHostTags();
                await loadAvailableTags();
                setSnackbarMessage(t('hostDetail.tagRemoved', 'Tag removed successfully'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                setSnackbarMessage(t('hostDetail.tagRemoveFailed', 'Failed to remove tag'));
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
            }
        } catch (error) {
            console.error('Error removing tag:', error);
            setSnackbarMessage(t('hostDetail.tagRemoveFailed', 'Failed to remove tag'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    return {
        hostTags,
        availableTags,
        selectedTagToAdd,
        setSelectedTagToAdd,
        handleAddTag,
        handleRemoveTag,
    };
};

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material';
import { TagWithHosts } from './settingsTypes';

interface SettingsDialogsProps {
  // Add Tag dialog
  addDialogOpen: boolean;
  onAddDialogClose: () => void;
  onCreateTag: () => void;
  // Edit Tag dialog
  editDialogOpen: boolean;
  onEditDialogClose: () => void;
  onUpdateTag: () => void;
  // Shared tag form fields
  tagName: string;
  setTagName: (value: string) => void;
  tagDescription: string;
  setTagDescription: (value: string) => void;
  // View Hosts dialog
  viewHostsDialogOpen: boolean;
  onViewHostsClose: () => void;
  viewingTag: TagWithHosts | null;
}

const SettingsDialogs: React.FC<SettingsDialogsProps> = ({
  addDialogOpen,
  onAddDialogClose,
  onCreateTag,
  editDialogOpen,
  onEditDialogClose,
  onUpdateTag,
  tagName,
  setTagName,
  tagDescription,
  setTagDescription,
  viewHostsDialogOpen,
  onViewHostsClose,
  viewingTag,
}) => {
  const { t } = useTranslation();

  return (
    <>
      {/* Add Tag Dialog */}
      <Dialog open={addDialogOpen} onClose={onAddDialogClose} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tags.addTag', 'Add Tag')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={t('tags.name', 'Name')}
            fullWidth
            variant="outlined"
            value={tagName}
            onChange={(e) => setTagName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label={t('tags.description', 'Description')}
            fullWidth
            variant="outlined"
            multiline
            rows={3}
            value={tagDescription}
            onChange={(e) => setTagDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={onAddDialogClose}>{t('common.cancel', 'Cancel')}</Button>
          <Button onClick={onCreateTag} variant="contained">{t('common.add', 'Add')}</Button>
        </DialogActions>
      </Dialog>

      {/* Edit Tag Dialog */}
      <Dialog open={editDialogOpen} onClose={onEditDialogClose} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tags.editTag', 'Edit Tag')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={t('tags.name', 'Name')}
            fullWidth
            variant="outlined"
            value={tagName}
            onChange={(e) => setTagName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label={t('tags.description', 'Description')}
            fullWidth
            variant="outlined"
            multiline
            rows={3}
            value={tagDescription}
            onChange={(e) => setTagDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={onEditDialogClose}>{t('common.cancel', 'Cancel')}</Button>
          <Button onClick={onUpdateTag} variant="contained">{t('common.save', 'Save')}</Button>
        </DialogActions>
      </Dialog>

      {/* View Hosts Dialog */}
      <Dialog open={viewHostsDialogOpen} onClose={onViewHostsClose} maxWidth="md" fullWidth>
        <DialogTitle>
          {t('tags.hostsAssociatedWith', 'Hosts associated with')} "{viewingTag?.name}"
        </DialogTitle>
        <DialogContent>
          {viewingTag?.hosts && viewingTag.hosts.length > 0 ? (
            <Box sx={{ mt: 1 }}>
              {viewingTag.hosts.map(host => (
                <Chip
                  key={host.id}
                  label={`${host.fqdn} (${host.ipv4})`}
                  variant="outlined"
                  sx={{ m: 0.5 }}
                  color={host.active ? 'primary' : 'default'}
                />
              ))}
            </Box>
          ) : (
            <Typography>{t('tags.noHostsAssociated', 'No hosts are associated with this tag.')}</Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={onViewHostsClose}>{t('common.close', 'Close')}</Button>
        </DialogActions>
      </Dialog>

    </>
  );
};

export default SettingsDialogs;

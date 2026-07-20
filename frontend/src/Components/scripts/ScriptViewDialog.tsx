// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import { IoTrash } from 'react-icons/io5';
import Editor from '@monaco-editor/react';
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from '@mui/material';
import { Script } from '../../Services/scripts';
import { getLanguageForShell, ShellOption } from './scriptsHelpers';

interface ScriptViewDialogProps {
  viewingScript: Script | null;
  allShells: ShellOption[];
  platforms: Array<{ value: string; label: string }>;
  canDeleteScript: boolean;
  canEditScript: boolean;
  formatTimestamp: (timestamp: string | undefined) => string;
  onClose: () => void;
  onDelete: (scriptId: string) => void;
  onEdit: (script: Script) => void;
}

const ScriptViewDialog: React.FC<ScriptViewDialogProps> = ({
  viewingScript,
  allShells,
  platforms,
  canDeleteScript,
  canEditScript,
  formatTimestamp,
  onClose,
  onDelete,
  onEdit,
}) => {
  const { t } = useTranslation();

  return (
    <Dialog
      open={!!viewingScript}
      onClose={onClose}
      maxWidth="md"
      fullWidth
    >
      {viewingScript && (
        <>
          <DialogTitle>
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              {viewingScript.name}
            </Typography>
          </DialogTitle>
          <DialogContent>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                <strong>{t('scripts.description')}:</strong> {viewingScript.description || t('common.noDescription')}
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                <Chip
                  label={allShells.find(s => s.value === viewingScript.shell_type)?.label || viewingScript.shell_type}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  label={platforms.find(p => p.value === viewingScript.platform)?.label || viewingScript.platform}
                  size="small"
                  variant="outlined"
                />
              </Box>
              <Typography variant="caption" display="block" gutterBottom>
                {t('scripts.updatedAt')}: {formatTimestamp(viewingScript.updated_at)}
              </Typography>
            </Box>

            <Typography variant="subtitle2" gutterBottom>
              {t('scripts.scriptContent')}
            </Typography>
            <Box sx={{ border: 1, borderColor: 'grey.300', borderRadius: 1 }}>
              <Editor
                height="400px"
                language={getLanguageForShell(viewingScript.shell_type)}
                value={viewingScript.content}
                theme="vs-dark"
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  fontSize: 14,
                  lineNumbers: 'on',
                  automaticLayout: true
                }}
              />
            </Box>
          </DialogContent>
          <DialogActions>
            {canDeleteScript && (
              <Button
                variant="outlined"
                color="error"
                startIcon={<IoTrash />}
                onClick={() => {
                  if (viewingScript.id) {
                    onDelete(viewingScript.id);
                    onClose();
                  }
                }}
              >
                {t('scripts.delete')}
              </Button>
            )}
            {canEditScript && (
              <Button
                variant="contained"
                onClick={() => onEdit(viewingScript)}
              >
                {t('scripts.edit')}
              </Button>
            )}
            <Button onClick={onClose}>
              {t('common.close')}
            </Button>
          </DialogActions>
        </>
      )}
    </Dialog>
  );
};

export default ScriptViewDialog;

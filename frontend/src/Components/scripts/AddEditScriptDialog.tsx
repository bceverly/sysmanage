// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import { IoSave } from 'react-icons/io5';
import Editor from '@monaco-editor/react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import { getLanguageForShell, ShellOption } from './scriptsHelpers';

interface AddEditScriptDialogProps {
  open: boolean;
  isEditMode: boolean;
  loading: boolean;
  scriptName: string;
  scriptDescription: string;
  scriptContent: string;
  selectedShell: string;
  selectedPlatform: string;
  shells: ShellOption[];
  platforms: Array<{ value: string; label: string }>;
  onScriptNameChange: (value: string) => void;
  onScriptDescriptionChange: (value: string) => void;
  onScriptContentChange: (value: string | undefined) => void;
  onShellChange: (value: string) => void;
  onPlatformChange: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
}

const AddEditScriptDialog: React.FC<AddEditScriptDialogProps> = ({
  open,
  isEditMode,
  loading,
  scriptName,
  scriptDescription,
  scriptContent,
  selectedShell,
  selectedPlatform,
  shells,
  platforms,
  onScriptNameChange,
  onScriptDescriptionChange,
  onScriptContentChange,
  onShellChange,
  onPlatformChange,
  onClose,
  onSave,
}) => {
  const { t } = useTranslation();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>
        <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
          {isEditMode ? t('scripts.edit') : t('scripts.addScript')}
        </Typography>
      </DialogTitle>
      <DialogContent>
        <Box sx={{ mt: 2 }}>
          <TextField
            fullWidth
            label={t('scripts.scriptName')}
            value={scriptName}
            onChange={(e) => onScriptNameChange(e.target.value)}
            margin="normal"
          />
          <TextField
            fullWidth
            label={t('scripts.description')}
            value={scriptDescription}
            onChange={(e) => onScriptDescriptionChange(e.target.value)}
            margin="normal"
            multiline
            rows={2}
          />

          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <FormControl fullWidth variant="outlined">
                <InputLabel id="shell-type-label">
                  {t('scripts.shellType')}
                </InputLabel>
                <Select
                  labelId="shell-type-label"
                  value={selectedShell}
                  label={t('scripts.shellType')}
                  onChange={(e) => onShellChange(e.target.value)}
                >
                  {shells.map((shell) => (
                    <MenuItem key={shell.value} value={shell.value}>
                      {shell.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <FormControl fullWidth variant="outlined">
                <InputLabel id="platform-label">
                  {t('scripts.platform')}
                </InputLabel>
                <Select
                  labelId="platform-label"
                  value={selectedPlatform}
                  label={t('scripts.platform')}
                  onChange={(e) => onPlatformChange(e.target.value)}
                >
                  {platforms.map((platform) => (
                    <MenuItem key={platform.value} value={platform.value}>
                      {platform.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </Box>

        <Typography variant="subtitle1" gutterBottom sx={{ mt: 2 }}>
          {t('scripts.scriptContent')}
        </Typography>
        <Box sx={{ border: 1, borderColor: 'grey.300', borderRadius: 1 }}>
          <Editor
            height="400px"
            language={getLanguageForShell(selectedShell)}
            value={scriptContent}
            onChange={onScriptContentChange}
            theme="vs-dark"
            options={{
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              fontSize: 14,
              lineNumbers: 'on',
              roundedSelection: false,
              automaticLayout: true
            }}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>
          {t('scripts.cancel')}
        </Button>
        <Button
          variant="contained"
          startIcon={<IoSave />}
          onClick={onSave}
          disabled={loading}
        >
          {isEditMode ? t('scripts.update') : t('scripts.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default AddEditScriptDialog;

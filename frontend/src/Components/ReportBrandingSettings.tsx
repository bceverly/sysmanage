import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CircularProgress,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  CloudUpload as CloudUploadIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import {
  ReportBranding,
  reportBrandingService,
} from '../Services/reportBranding';

const ReportBrandingSettings: React.FC = () => {
  const { t } = useTranslation();

  const [branding, setBranding] = useState<ReportBranding | null>(null);
  const [companyName, setCompanyName] = useState('');
  const [headerText, setHeaderText] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [logoBust, setLogoBust] = useState<number>(0);

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const showSuccess = (msg: string) => {
    setSnackbarMessage(msg);
    setSnackbarSeverity('success');
    setSnackbarOpen(true);
  };
  const showError = (msg: string) => {
    setSnackbarMessage(msg);
    setSnackbarSeverity('error');
    setSnackbarOpen(true);
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const b = await reportBrandingService.get();
      setBranding(b);
      setCompanyName(b.company_name ?? '');
      setHeaderText(b.header_text ?? '');
      setLogoBust(Date.now());
    } catch (e) {
      console.error(e);
      showError(t('reportBranding.loadError', 'Failed to load report branding'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await reportBrandingService.update({
        company_name: companyName.trim(),
        header_text: headerText.trim(),
      });
      setBranding(updated);
      showSuccess(t('reportBranding.saved', 'Branding saved'));
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('reportBranding.saveError', 'Failed to save branding'));
    } finally {
      setSaving(false);
    }
  };

  const handlePickFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const updated = await reportBrandingService.uploadLogo(file);
      setBranding(updated);
      setLogoBust(Date.now());
      showSuccess(t('reportBranding.logoUploaded', 'Logo uploaded'));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('reportBranding.uploadError', 'Logo upload failed'));
    } finally {
      // Reset the input so re-uploading the same file fires onChange.
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDeleteLogo = async () => {
    if (!globalThis.confirm(t('reportBranding.confirmRemoveLogo', 'Remove the current logo?'))) {
      return;
    }
    try {
      const updated = await reportBrandingService.deleteLogo();
      setBranding(updated);
      setLogoBust(Date.now());
      showSuccess(t('reportBranding.logoRemoved', 'Logo removed'));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('reportBranding.deleteError', 'Failed to remove logo'));
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Card>
        <CardHeader
          title={t('reportBranding.title', 'Report Branding')}
          subheader={t(
            'reportBranding.subtitle',
            'Org logo and header text injected into every generated PDF/HTML report',
          )}
        />
        <CardContent>
          <Stack spacing={2}>
            <TextField
              label={t('reportBranding.companyName', 'Company Name')}
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              fullWidth
              slotProps={{ htmlInput: { maxLength: 255 } }}
            />
            <TextField
              label={t('reportBranding.headerText', 'Header Text')}
              value={headerText}
              onChange={(e) => setHeaderText(e.target.value)}
              fullWidth
              multiline
              rows={2}
              slotProps={{ htmlInput: { maxLength: 500 } }}
              helperText={t(
                'reportBranding.headerTextHelp',
                'Appears alongside the logo in the report header (e.g. "Confidential — Internal Use").',
              )}
            />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Box
                sx={{
                  width: 220,
                  height: 96,
                  border: '1px dashed',
                  borderColor: 'divider',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  bgcolor: 'background.default',
                  borderRadius: 1,
                }}
              >
                {branding?.has_logo ? (
                  <img
                    src={reportBrandingService.logoUrl(logoBust)}
                    alt={t('reportBranding.logoAlt', 'Report logo')}
                    style={{
                      maxWidth: '100%',
                      maxHeight: '100%',
                      objectFit: 'contain',
                    }}
                  />
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {t('reportBranding.noLogo', 'No logo set')}
                  </Typography>
                )}
              </Box>
              <Stack spacing={1}>
                <Button
                  variant="outlined"
                  startIcon={<CloudUploadIcon />}
                  onClick={handlePickFile}
                >
                  {branding?.has_logo
                    ? t('reportBranding.replaceLogo', 'Replace Logo')
                    : t('reportBranding.uploadLogo', 'Upload Logo')}
                </Button>
                {branding?.has_logo && (
                  <Button
                    variant="outlined"
                    color="error"
                    startIcon={<DeleteIcon />}
                    onClick={handleDeleteLogo}
                  >
                    {t('reportBranding.removeLogo', 'Remove Logo')}
                  </Button>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/svg+xml,image/webp"
                  style={{ display: 'none' }}
                  onChange={handleFileChosen}
                />
              </Stack>
            </Box>
            <Alert severity="info">
              {t(
                'reportBranding.constraintsHelp',
                'Allowed formats: PNG, JPEG, SVG, WEBP. Maximum size: 1 MB.',
              )}
            </Alert>
            <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button
                variant="contained"
                startIcon={saving ? <CircularProgress size={16} /> : <SaveIcon />}
                onClick={handleSave}
                disabled={saving}
              >
                {t('common.save', 'Save')}
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      <Snackbar
        open={snackbarOpen}
        autoHideDuration={4000}
        onClose={() => setSnackbarOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          severity={snackbarSeverity}
          onClose={() => setSnackbarOpen(false)}
          variant="filled"
        >
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default ReportBrandingSettings;

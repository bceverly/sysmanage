import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  FormGroup,
  FormControlLabel,
  Checkbox,
  Box,
  Typography,
  CircularProgress,
  Alert,
} from '@mui/material';
import { Settings as SettingsIcon } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';

interface DashboardCard {
  identifier: string;
  label: string;
  visible: boolean;
}

interface DashboardSettingsDialogProps {
  open: boolean;
  onClose: () => void;
  onSave: (cards: DashboardCard[]) => void;
}

const DashboardSettingsDialog: React.FC<DashboardSettingsDialogProps> = ({
  open,
  onClose,
  onSave,
}) => {
  const { t } = useTranslation();
  const [cards, setCards] = useState<DashboardCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Available dashboard cards
  const availableCards: { identifier: string; label: string }[] = [
    { identifier: 'hosts', label: t('dashboard.hosts', 'Hosts') },
    { identifier: 'updates', label: t('dashboard.updates', 'Updates') },
    { identifier: 'security', label: t('dashboard.security', 'Security') },
    { identifier: 'reboot', label: t('dashboard.rebootRequired', 'Reboot Needed') },
    { identifier: 'antivirus', label: t('dashboard.antivirusCoverage', 'Antivirus') },
    { identifier: 'opentelemetry', label: t('dashboard.openTelemetryCoverage', 'OpenTelemetry') },
  ];

  useEffect(() => {
    if (open) {
      loadPreferences();
    }
  }, [open]); // loadPreferences is defined in the component, stable function

  const loadPreferences = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axiosInstance.get('/api/user-preferences/dashboard-cards');

      // Create a map of saved preferences
      const savedPrefs = new Map(
        response.data.preferences.map((pref: { card_identifier: string; visible: boolean }) => [pref.card_identifier, pref.visible])
      );

      // Merge with available cards (default to visible if not saved)
      const mergedCards = availableCards.map((card) => ({
        identifier: card.identifier,
        label: card.label,
        visible: savedPrefs.has(card.identifier) ? savedPrefs.get(card.identifier)! : true,
      }));

      setCards(mergedCards);
    } catch (err) {
      console.error('Error loading dashboard preferences:', err);
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Failed to load preferences');
      // Default to all visible on error
      setCards(
        availableCards.map((card) => ({
          ...card,
          visible: true,
        }))
      );
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = (identifier: string) => {
    setCards((prevCards) =>
      prevCards.map((card) =>
        card.identifier === identifier ? { ...card, visible: !card.visible } : card
      )
    );
  };

  const handleCheckAll = () => {
    setCards((prevCards) => prevCards.map((card) => ({ ...card, visible: true })));
  };

  const handleCheckNone = () => {
    setCards((prevCards) => prevCards.map((card) => ({ ...card, visible: false })));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);

      await axiosInstance.put('/api/user-preferences/dashboard-cards', {
        preferences: cards.map((card) => ({
          card_identifier: card.identifier,
          visible: card.visible,
        })),
      });

      onSave(cards);
      onClose();
    } catch (err) {
      console.error('Error saving dashboard preferences:', err);
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Failed to save preferences');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Box display="flex" alignItems="center" gap={1}>
          <SettingsIcon />
          <Typography variant="h6">
            {t('dashboard.settings.title', 'Dashboard Settings')}
          </Typography>
        </Box>
      </DialogTitle>

      <DialogContent>
        {loading ? (
          <Box display="flex" justifyContent="center" py={3}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}

            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {t(
                'dashboard.settings.description',
                'Select which cards to display on your dashboard'
              )}
            </Typography>

            <Box display="flex" gap={1} mb={2}>
              <Button variant="outlined" size="small" onClick={handleCheckAll}>
                {t('dashboard.settings.checkAll', 'Check All')}
              </Button>
              <Button variant="outlined" size="small" onClick={handleCheckNone}>
                {t('dashboard.settings.checkNone', 'Check None')}
              </Button>
            </Box>

            <FormGroup>
              {cards.map((card) => (
                <FormControlLabel
                  key={card.identifier}
                  control={
                    <Checkbox
                      checked={card.visible}
                      onChange={() => handleToggle(card.identifier)}
                    />
                  }
                  label={card.label}
                />
              ))}
            </FormGroup>
          </>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          {t('common.cancel', 'Cancel')}
        </Button>
        <Button onClick={handleSave} variant="contained" disabled={loading || saving}>
          {saving ? (
            <>
              <CircularProgress size={20} sx={{ mr: 1 }} />
              {t('common.saving', 'Saving...')}
            </>
          ) : (
            t('common.save', 'Save')
          )}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default DashboardSettingsDialog;

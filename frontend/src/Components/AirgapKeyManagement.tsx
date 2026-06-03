/**
 * Air-gap signing-key cards for Settings → Server Role.
 *
 *   * CollectorPublicKeyCard  — shown when role = collector.  Displays
 *     this server's collector PUBLIC key + fingerprint with a one-click
 *     copy so the operator can hand it to a repository.  (The private
 *     signing key never leaves the box / is never exposed here.)
 *   * TrustedCollectorsCard   — shown when role = repository.  Import /
 *     list / remove the collector public keys this repository trusts
 *     when verifying signed media.
 *
 * Backed by /api/v1/airgap/collector-key and
 * /api/v1/airgap/trusted-collectors.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  IconButton,
  InputLabel,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Select,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DeleteIcon from '@mui/icons-material/Delete';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useTranslation } from 'react-i18next';

import axiosInstance from '../Services/api';

const COLLECTOR_KEY_URL = '/api/v1/airgap/collector-key';
const TRUSTED_URL = '/api/v1/airgap/trusted-collectors';
const DEVICES_URL = '/api/v1/airgap/block-devices';
const IMPORT_DEVICE_URL = '/api/v1/airgap/import-device';

interface BlockDevice {
  name: string;
  path: string;
  type: string;
  size_bytes: number | null;
  removable: boolean;
  label: string | null;
  fstype: string | null;
  is_optical: boolean;
}

const fmtBytes = (n: number | null): string => {
  if (n == null) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
};

interface CollectorKey {
  public_key_pem: string;
  fingerprint: string;
}

interface TrustedCollector {
  name: string;
  fingerprint: string | null;
}

const cardSx = {
  border: 1,
  borderColor: 'divider',
  borderRadius: 1,
  p: 2,
  mt: 2,
} as const;

const monoSx = {
  fontFamily: 'monospace',
  fontSize: '0.8rem',
  wordBreak: 'break-all',
} as const;

export const CollectorPublicKeyCard: React.FC = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [key, setKey] = useState<CollectorKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const r = await axiosInstance.get<CollectorKey>(COLLECTOR_KEY_URL);
        if (alive) {
          setKey(r.data);
          setError(null);
        }
      } catch (e: unknown) {
        const detail = (e as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail;
        if (alive) {
          setError(
            detail ||
              t(
                'airgapKeys.collector.loadError',
                'Could not load the collector public key.',
              ),
          );
        }
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [t]);

  const copy = async (value: string, what: string) => {
    try {
      await globalThis.navigator.clipboard.writeText(value);
      setCopied(what);
      globalThis.setTimeout(() => setCopied(null), 2000);
    } catch {
      setError(t('airgapKeys.copyError', 'Could not copy to clipboard.'));
    }
  };

  return (
    <Box sx={cardSx}>
      <Typography variant="subtitle1" gutterBottom>
        {t('airgapKeys.collector.title', 'Collector Public Key')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {t(
          'airgapKeys.collector.help',
          'Copy this public key and import it on the Air-Gap Repository server so it will trust the signed media this collector produces. Only the public key is shown — the private signing key never leaves this server.',
        )}
      </Typography>

      {loading && <CircularProgress size={20} />}

      {!loading && error && <Alert severity="info">{error}</Alert>}

      {!loading && key && (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {t('airgapKeys.fingerprint', 'Fingerprint')}:
            </Typography>
            <Typography sx={monoSx}>{key.fingerprint}</Typography>
            <Tooltip
              title={
                copied === 'fp'
                  ? t('airgapKeys.copied', 'Copied!')
                  : t('airgapKeys.copyFingerprint', 'Copy fingerprint')
              }
            >
              <IconButton size="small" onClick={() => copy(key.fingerprint, 'fp')}>
                <ContentCopyIcon fontSize="inherit" />
              </IconButton>
            </Tooltip>
          </Box>
          <TextField
            value={key.public_key_pem}
            multiline
            fullWidth
            minRows={4}
            maxRows={8}
            InputProps={{ readOnly: true, sx: monoSx }}
          />
          <Button
            sx={{ mt: 1 }}
            variant="outlined"
            size="small"
            startIcon={<ContentCopyIcon />}
            onClick={() => copy(key.public_key_pem, 'pem')}
          >
            {copied === 'pem'
              ? t('airgapKeys.copied', 'Copied!')
              : t('airgapKeys.collector.copyKey', 'Copy Public Key')}
          </Button>
        </Box>
      )}
    </Box>
  );
};

export const TrustedCollectorsCard: React.FC = () => {
  const { t } = useTranslation();
  const [trusted, setTrusted] = useState<TrustedCollector[]>([]);
  const [name, setName] = useState('');
  const [pem, setPem] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await axiosInstance.get<{ trusted: TrustedCollector[] }>(
        TRUSTED_URL,
      );
      setTrusted(r.data.trusted || []);
    } catch {
      setError(
        t('airgapKeys.trusted.loadError', 'Could not load trusted keys.'),
      );
    }
  }, [t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const doImport = async () => {
    if (!name.trim() || !pem.trim()) {
      setError(
        t('airgapKeys.trusted.required', 'Name and public key are both required.'),
      );
      return;
    }
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      const r = await axiosInstance.post<TrustedCollector>(TRUSTED_URL, {
        name: name.trim(),
        public_key_pem: pem,
      });
      setOk(
        t('airgapKeys.trusted.imported', 'Imported key {{fp}}', {
          fp: (r.data.fingerprint || '').slice(0, 16),
        }),
      );
      setName('');
      setPem('');
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(
        detail || t('airgapKeys.trusted.importError', 'Could not import key.'),
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async (n: string) => {
    try {
      await axiosInstance.delete(`${TRUSTED_URL}/${encodeURIComponent(n)}`);
      await refresh();
    } catch {
      setError(t('airgapKeys.trusted.removeError', 'Could not remove key.'));
    }
  };

  return (
    <Box sx={cardSx}>
      <Typography variant="subtitle1" gutterBottom>
        {t('airgapKeys.trusted.title', 'Trusted Collector Keys')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {t(
          'airgapKeys.trusted.help',
          'Import the public key from each Air-Gap Collector whose media this repository should accept. Media signed by an untrusted key is rejected during ingest.',
        )}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {ok && (
        <Alert severity="success" sx={{ mb: 1 }} onClose={() => setOk(null)}>
          {ok}
        </Alert>
      )}

      <List dense>
        {trusted.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ ml: 1 }}>
            {t('airgapKeys.trusted.empty', 'No trusted collector keys yet.')}
          </Typography>
        )}
        {trusted.map((row) => (
          <ListItem
            key={row.name}
            secondaryAction={
              <IconButton edge="end" size="small" onClick={() => remove(row.name)}>
                <DeleteIcon fontSize="inherit" />
              </IconButton>
            }
          >
            <ListItemText
              primary={row.name}
              secondary={
                <Typography component="span" sx={monoSx}>
                  {row.fingerprint || t('airgapKeys.trusted.badKey', '(unreadable key)')}
                </Typography>
              }
            />
          </ListItem>
        ))}
      </List>

      <Box sx={{ mt: 1 }}>
        <TextField
          label={t('airgapKeys.trusted.nameLabel', 'Collector name')}
          value={name}
          onChange={(e) => setName(e.target.value)}
          size="small"
          fullWidth
          sx={{ mb: 1 }}
        />
        <TextField
          label={t('airgapKeys.trusted.pemLabel', 'Public key (PEM)')}
          value={pem}
          onChange={(e) => setPem(e.target.value)}
          placeholder={'-----BEGIN PUBLIC KEY-----\n…\n-----END PUBLIC KEY-----'}
          multiline
          minRows={4}
          fullWidth
          InputProps={{ sx: monoSx }}
        />
        <Button
          sx={{ mt: 1 }}
          variant="contained"
          size="small"
          onClick={doImport}
          disabled={busy}
          startIcon={busy ? <CircularProgress size={16} /> : undefined}
        >
          {t('airgapKeys.trusted.import', 'Import Key')}
        </Button>
      </Box>

      {trusted.length > 0 && (
        <Chip
          sx={{ mt: 1, ml: 1 }}
          size="small"
          label={t('airgapKeys.trusted.count', '{{n}} trusted', {
            n: trusted.length,
          })}
        />
      )}
    </Box>
  );
};

export const ImportDeviceCard: React.FC = () => {
  const { t } = useTranslation();
  const [devices, setDevices] = useState<BlockDevice[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const r = await axiosInstance.get<{
        devices: BlockDevice[];
        selected: string | null;
        default: string | null;
      }>(DEVICES_URL);
      setDevices(r.data.devices || []);
      // Prefer the saved choice; otherwise fall back to the server's
      // suggested default (lowest optical) so the field isn't blank.
      setSelected(r.data.selected || r.data.default || '');
      setError(null);
    } catch {
      setError(t('airgapDevices.loadError', 'Could not enumerate drives.'));
    } finally {
      setBusy(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const persist = async (device: string) => {
    setSelected(device);
    try {
      await axiosInstance.put(IMPORT_DEVICE_URL, { device: device || null });
      setError(null);
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(detail || t('airgapDevices.saveError', 'Could not save device.'));
    }
  };

  return (
    <Box sx={cardSx}>
      <Typography variant="subtitle1" gutterBottom>
        {t('airgapDevices.title', 'Import Drive')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {t(
          'airgapDevices.help',
          'Pick the optical/USB drive that holds the collector media. The Import button on the Air-Gap Repositories page becomes available when this drive has a readable ISO inserted. The media signature is verified during import.',
        )}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <FormControl size="small" sx={{ minWidth: 280 }}>
          <InputLabel id="airgap-device-label">
            {t('airgapDevices.label', 'Block device')}
          </InputLabel>
          <Select
            labelId="airgap-device-label"
            label={t('airgapDevices.label', 'Block device')}
            value={selected}
            onChange={(e) => persist(e.target.value as string)}
          >
            <MenuItem value="">
              <em>{t('airgapDevices.none', '(none)')}</em>
            </MenuItem>
            {devices.map((d) => (
              <MenuItem key={d.path} value={d.path}>
                {d.path}
                {d.is_optical ? ' · optical' : d.removable ? ' · removable' : ''}
                {d.size_bytes ? ` · ${fmtBytes(d.size_bytes)}` : ''}
                {d.label ? ` · ${d.label}` : ''}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Tooltip title={t('airgapDevices.rescan', 'Rescan drives')}>
          <span>
            <IconButton onClick={load} disabled={busy}>
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      {devices.length === 0 && !busy && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          {t(
            'airgapDevices.empty',
            'No eligible drives found. Insert media and press Rescan.',
          )}
        </Typography>
      )}
    </Box>
  );
};

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import {
  listTrackedImages,
  trackImage,
  untrackImage,
  MirrorRepository,
  MirrorImageContent,
  ImageCaptureStatus,
} from '../../Services/repositoryMirroring';

// ---------------------------------------------------------------------
// Tracked-images expand row (Phase 17.2 — OCI image content lifecycle)
//
// One inline collapsible per mirror listing the container images tracked for
// capture (registry/repository:tag + captured digest + capture status), with a
// small "track image" form and an untrack action per row.  Loads lazily on
// expand and re-polls every 10s so a DISPATCHED -> CAPTURED transition (after
// "Capture images") — which also fills the pinned digest — appears without a
// manual refresh.  Modeled 1:1 on TrackedSnapsExpandRow (Phase 17.1).
// ---------------------------------------------------------------------

const STATUS_COLOR: Record<
  ImageCaptureStatus,
  'default' | 'info' | 'success' | 'error'
> = {
  TRACKED: 'default',
  DISPATCHED: 'info',
  CAPTURED: 'success',
  FAILED: 'error',
};

// A captured digest is "sha256:<64 hex>"; show a readable stem in the table and
// keep the full value in a tooltip.
const shortDigest = (digest?: string | null): string => {
  if (!digest) return '—';
  const [algo, hex] = digest.split(':');
  return hex ? `${algo}:${hex.slice(0, 12)}` : digest.slice(0, 19);
};

interface TrackedImagesExpandRowProps {
  mirror: MirrorRepository;
  colSpan: number;
  expanded: boolean;
}

const TrackedImagesExpandRow: React.FC<TrackedImagesExpandRowProps> = ({
  mirror,
  colSpan,
  expanded,
}) => {
  const { t } = useTranslation();
  const [images, setImages] = useState<MirrorImageContent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [registry, setRegistry] = useState('docker.io');
  const [repository, setRepository] = useState('');
  const [tag, setTag] = useState('latest');
  const [busy, setBusy] = useState(false);

  const fetchImages = React.useCallback(async () => {
    try {
      setImages(await listTrackedImages(mirror.id));
      setError(null);
    } catch {
      setError(t('mirror.image.loadError', 'Could not load tracked images.'));
    }
  }, [mirror.id, t]);

  useEffect(() => {
    if (!expanded) return undefined;
    fetchImages();
    const handle = setInterval(fetchImages, 10_000);
    return () => clearInterval(handle);
  }, [expanded, fetchImages]);

  const add = async () => {
    const repo = repository.trim();
    if (!repo) return;
    setBusy(true);
    try {
      await trackImage(mirror.id, {
        registry: registry.trim() || 'docker.io',
        repository: repo,
        tag: tag.trim() || 'latest',
      });
      setRepository('');
      await fetchImages();
    } catch {
      setError(
        t(
          'mirror.image.trackError',
          'Could not track that image. Use registry host, lowercase repository, and a valid tag.',
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async (image: MirrorImageContent) => {
    try {
      await untrackImage(mirror.id, image.id);
      await fetchImages();
    } catch {
      setError(t('mirror.image.untrackError', 'Could not untrack that image.'));
    }
  };

  return (
    <TableRow>
      <TableCell
        colSpan={colSpan}
        sx={{ py: 0, borderBottom: expanded ? undefined : 'none' }}
      >
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          <Box sx={{ py: 1, pl: 4, pr: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {t('mirror.image.title', 'Tracked images for {{name}}', {
                name: mirror.name,
              })}
            </Typography>
            {error && (
              <Alert severity="error" sx={{ mb: 1 }}>
                {error}
              </Alert>
            )}
            <Stack
              direction="row"
              spacing={1}
              sx={{ mb: 1 }}
              alignItems="center"
            >
              <TextField
                size="small"
                label={t('mirror.image.registry', 'Registry')}
                value={registry}
                onChange={(e) => setRegistry(e.target.value)}
                placeholder="docker.io"
              />
              <TextField
                size="small"
                label={t('mirror.image.repository', 'Repository')}
                value={repository}
                onChange={(e) => setRepository(e.target.value)}
                placeholder="library/nginx"
              />
              <TextField
                size="small"
                label={t('mirror.image.tag', 'Tag')}
                value={tag}
                onChange={(e) => setTag(e.target.value)}
                placeholder="latest"
              />
              <Button
                size="small"
                variant="outlined"
                startIcon={<AddIcon />}
                disabled={busy || !repository.trim()}
                onClick={add}
              >
                {t('mirror.image.track', 'Track')}
              </Button>
            </Stack>
            {images?.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                {t(
                  'mirror.image.empty',
                  'No images tracked yet. Add one above, then use "Capture images".',
                )}
              </Typography>
            )}
            {images && images.length > 0 && (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>
                      {t('mirror.image.col.image', 'Image')}
                    </TableCell>
                    <TableCell>{t('mirror.image.col.tag', 'Tag')}</TableCell>
                    <TableCell>
                      {t('mirror.image.col.digest', 'Digest')}
                    </TableCell>
                    <TableCell>
                      {t('mirror.image.col.status', 'Capture')}
                    </TableCell>
                    <TableCell align="right">
                      {t('mirror.image.col.actions', 'Actions')}
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {images.map((img) => (
                    <TableRow key={img.id}>
                      <TableCell sx={{ fontFamily: 'monospace' }}>
                        {img.registry}/{img.repository}
                      </TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>
                        {img.tag}
                      </TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>
                        <Tooltip
                          title={img.digest || ''}
                          arrow
                          disableHoverListener={!img.digest}
                        >
                          <span>{shortDigest(img.digest)}</span>
                        </Tooltip>
                      </TableCell>
                      <TableCell>
                        <Tooltip
                          title={img.error_message || ''}
                          arrow
                          disableHoverListener={!img.error_message}
                        >
                          <Chip
                            size="small"
                            label={img.capture_status}
                            color={STATUS_COLOR[img.capture_status]}
                          />
                        </Tooltip>
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip
                          title={t(
                            'mirror.image.untrack',
                            'Stop tracking this image',
                          )}
                          arrow
                        >
                          <IconButton size="small" onClick={() => remove(img)}>
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Box>
        </Collapse>
      </TableCell>
    </TableRow>
  );
};

export default TrackedImagesExpandRow;

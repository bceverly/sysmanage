// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from 'react';
import { Chip, CircularProgress, Tooltip } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { formatElapsed } from './helpers';

// ---------------------------------------------------------------------
// Per-action status chip
//
// Each mirror has five independent action lifecycles (sync, snapshot,
// restore, integrity, gc) that the old UI flattened onto one
// ``last_sync_status`` column.  This chip renders ONE action's state:
//
//   never run        → muted "—"
//   DISPATCHED + msg → spinner + "Nm ago" elapsed-time
//   SUCCESS          → green chip with absolute timestamp on hover
//   FAILED           → red chip; hover reveals the full error text
//
// The chip is keyed off ``message_id`` (not ``status``) for the
// in-flight check because the dispatch endpoints stamp message_id at
// dispatch and the result handler clears it on success OR failure —
// which means message_id is the load-bearing "is this still in
// flight" signal.  ``status`` alone can lie (the DISPATCHED string
// might linger on a stuck row whose result handler never fired).
// ---------------------------------------------------------------------

interface ActionStatusChipProps {
  label: string;
  status: string | null | undefined;
  errorText: string | null | undefined;
  inFlightMessageId: string | null | undefined;
  at: string | null | undefined;
}

const ActionStatusChip: React.FC<ActionStatusChipProps> = ({
  label, status, errorText, inFlightMessageId, at,
}) => {
  const { t } = useTranslation();
  const atDate = at ? new Date(at) : null;
  const inFlight = !!inFlightMessageId;

  // Tick once per second WHILE in-flight so the elapsed-time label
  // advances smoothly.  ``formatElapsed`` reads ``Date.now()`` at
  // render, so the only thing missing was a reason to re-render
  // between the parent's 10s data polls — this forces one every
  // second.  The interval is torn down the moment the op settles
  // (inFlight flips false), so idle chips never hold a timer.  Hooks
  // run unconditionally before the early returns below, per the rules
  // of hooks.
  const [, setTick] = useState(0); // NOSONAR S6754 - re-render tick; value intentionally unused
  useEffect(() => {
    if (!inFlight) return undefined;
    const handle = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(handle);
  }, [inFlight]);

  if (inFlight) {
    const elapsed = atDate ? formatElapsed(atDate) : '';
    return (
      <Tooltip
        title={t('mirror.chip.inFlight', '{{label}} in progress since {{at}}', {
          label,
          at: atDate ? atDate.toLocaleString() : 'unknown time',
        })}
        arrow
      >
        <Chip
          size="small"
          icon={<CircularProgress size={10} thickness={6} sx={{ ml: 1, color: 'inherit !important' }} />}
          label={elapsed ? `${label} · ${elapsed}` : label}
          color="info"
          variant="outlined"
        />
      </Tooltip>
    );
  }

  if (!status) {
    return (
      <Chip
        size="small"
        label={label}
        variant="outlined"
        sx={{ opacity: 0.4 }}
      />
    );
  }

  if (status === 'FAILED') {
    return (
      <Tooltip
        title={errorText || t('mirror.chip.failedNoText', 'Failed; no error text returned.')}
        arrow
        placement="top"
        slotProps={{
          tooltip: {
            sx: {
              whiteSpace: 'pre-wrap',
              maxWidth: 600,
              fontFamily: 'monospace',
              fontSize: '0.75rem',
            },
          },
        }}
      >
        <Chip
          size="small"
          label={`${label} · ${t('mirror.chip.failed', 'failed')}`}
          color="error"
          sx={{ cursor: 'help' }}
        />
      </Tooltip>
    );
  }

  if (status === 'SUCCESS') {
    return (
      <Tooltip
        title={atDate ? atDate.toLocaleString() : ''}
        arrow
        placement="top"
      >
        <Chip
          size="small"
          label={`${label} · ${t('mirror.chip.ok', 'ok')}`}
          color="success"
          variant="outlined"
        />
      </Tooltip>
    );
  }

  // Any other state (e.g. ``DISPATCHED`` without a message_id, which
  // shouldn't happen but might if a buggy migration partially-fills
  // the row).  Fall back to a neutral chip with the raw status.
  return <Chip size="small" label={`${label} · ${status}`} variant="outlined" />;
};

export default ActionStatusChip;

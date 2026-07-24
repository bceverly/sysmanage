// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, beforeEach, test, expect } from 'vitest';

vi.mock('react-i18next', () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = fallback || key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, 'g'), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: 'en' } }) };
});

vi.mock('../../Services/repositoryMirroring', () => ({
  listTrackedSnaps: vi.fn(),
  trackSnap: vi.fn(),
  untrackSnap: vi.fn(),
}));

import {
  listTrackedSnaps,
  trackSnap,
  untrackSnap,
} from '../../Services/repositoryMirroring';
import TrackedSnapsExpandRow from './TrackedSnapsExpandRow';

const mockList = listTrackedSnaps as unknown as ReturnType<typeof vi.fn>;
const mockTrack = trackSnap as unknown as ReturnType<typeof vi.fn>;
const mockUntrack = untrackSnap as unknown as ReturnType<typeof vi.fn>;

const MIRROR = { id: 'm1', name: 'ubuntu-noble' } as unknown as Parameters<
  typeof TrackedSnapsExpandRow
>[0]['mirror'];

function renderRow(expanded = true) {
  return render(
    <table>
      <tbody>
        <TrackedSnapsExpandRow mirror={MIRROR} colSpan={9} expanded={expanded} />
      </tbody>
    </table>,
  );
}

beforeEach(() => vi.clearAllMocks());

test('lists tracked snaps (name, channel, capture status) when expanded', async () => {
  mockList.mockResolvedValue([
    {
      id: 's1',
      snap_name: 'hello',
      channel: 'latest/stable',
      capture_status: 'CAPTURED',
    },
  ]);
  renderRow(true);
  expect(await screen.findByText('hello')).toBeTruthy();
  expect(screen.getByText('latest/stable')).toBeTruthy();
  expect(screen.getByText('CAPTURED')).toBeTruthy();
  expect(mockList).toHaveBeenCalledWith('m1');
});

test('does not fetch when collapsed', () => {
  renderRow(false);
  expect(mockList).not.toHaveBeenCalled();
});

test('shows the empty state when nothing is tracked', async () => {
  mockList.mockResolvedValue([]);
  renderRow(true);
  expect(await screen.findByText(/No snaps tracked yet/i)).toBeTruthy();
});

test('tracks a new snap with name + default channel', async () => {
  mockList.mockResolvedValue([]);
  mockTrack.mockResolvedValue({
    id: 's1',
    snap_name: 'core20',
    channel: 'latest/stable',
    capture_status: 'TRACKED',
  });
  renderRow(true);
  await screen.findByText(/No snaps tracked yet/i);
  fireEvent.change(screen.getByPlaceholderText('hello'), {
    target: { value: 'core20' },
  });
  fireEvent.click(screen.getByText('Track'));
  await waitFor(() =>
    expect(mockTrack).toHaveBeenCalledWith('m1', {
      snap_name: 'core20',
      channel: 'latest/stable',
    }),
  );
});

test('untracks a snap via the delete action', async () => {
  mockList.mockResolvedValue([
    {
      id: 's1',
      snap_name: 'hello',
      channel: 'latest/stable',
      capture_status: 'TRACKED',
    },
  ]);
  mockUntrack.mockResolvedValue(undefined);
  renderRow(true);
  await screen.findByText('hello');
  const buttons = screen.getAllByRole('button');
  fireEvent.click(buttons[buttons.length - 1]); // per-row delete (untrack)
  await waitFor(() => expect(mockUntrack).toHaveBeenCalledWith('m1', 's1'));
});

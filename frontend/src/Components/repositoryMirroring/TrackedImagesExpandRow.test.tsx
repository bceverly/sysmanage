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
  listTrackedImages: vi.fn(),
  trackImage: vi.fn(),
  untrackImage: vi.fn(),
}));

import {
  listTrackedImages,
  trackImage,
  untrackImage,
} from '../../Services/repositoryMirroring';
import TrackedImagesExpandRow from './TrackedImagesExpandRow';

const mockList = listTrackedImages as unknown as ReturnType<typeof vi.fn>;
const mockTrack = trackImage as unknown as ReturnType<typeof vi.fn>;
const mockUntrack = untrackImage as unknown as ReturnType<typeof vi.fn>;

const MIRROR = { id: 'm1', name: 'ubuntu-noble' } as unknown as Parameters<
  typeof TrackedImagesExpandRow
>[0]['mirror'];

function renderRow(expanded = true) {
  return render(
    <table>
      <tbody>
        <TrackedImagesExpandRow mirror={MIRROR} colSpan={9} expanded={expanded} />
      </tbody>
    </table>,
  );
}

beforeEach(() => vi.clearAllMocks());

test('lists tracked images (ref, tag, digest, capture status) when expanded', async () => {
  mockList.mockResolvedValue([
    {
      id: 'i1',
      registry: 'docker.io',
      repository: 'library/nginx',
      tag: '1.27',
      digest: 'sha256:deadbeef0000111122223333444455556666777788889999aaaabbbbccccdddd',
      capture_status: 'CAPTURED',
    },
  ]);
  renderRow(true);
  expect(await screen.findByText('docker.io/library/nginx')).toBeTruthy();
  expect(screen.getByText('1.27')).toBeTruthy();
  expect(screen.getByText('CAPTURED')).toBeTruthy();
  // digest shown truncated to a readable stem
  expect(screen.getByText('sha256:deadbeef0000')).toBeTruthy();
  expect(mockList).toHaveBeenCalledWith('m1');
});

test('does not fetch when collapsed', () => {
  renderRow(false);
  expect(mockList).not.toHaveBeenCalled();
});

test('shows the empty state when nothing is tracked', async () => {
  mockList.mockResolvedValue([]);
  renderRow(true);
  expect(await screen.findByText(/No images tracked yet/i)).toBeTruthy();
});

test('tracks a new image with registry + repository + default tag', async () => {
  mockList.mockResolvedValue([]);
  mockTrack.mockResolvedValue({
    id: 'i1',
    registry: 'docker.io',
    repository: 'library/nginx',
    tag: 'latest',
    capture_status: 'TRACKED',
  });
  renderRow(true);
  await screen.findByText(/No images tracked yet/i);
  fireEvent.change(screen.getByPlaceholderText('library/nginx'), {
    target: { value: 'library/nginx' },
  });
  fireEvent.click(screen.getByText('Track'));
  await waitFor(() =>
    expect(mockTrack).toHaveBeenCalledWith('m1', {
      registry: 'docker.io',
      repository: 'library/nginx',
      tag: 'latest',
    }),
  );
});

test('untracks an image via the delete action', async () => {
  mockList.mockResolvedValue([
    {
      id: 'i1',
      registry: 'quay.io',
      repository: 'org/app',
      tag: 'v2',
      digest: null,
      capture_status: 'TRACKED',
    },
  ]);
  mockUntrack.mockResolvedValue(undefined);
  renderRow(true);
  await screen.findByText('quay.io/org/app');
  const buttons = screen.getAllByRole('button');
  fireEvent.click(buttons[buttons.length - 1]); // per-row delete (untrack)
  await waitFor(() => expect(mockUntrack).toHaveBeenCalledWith('m1', 'i1'));
});

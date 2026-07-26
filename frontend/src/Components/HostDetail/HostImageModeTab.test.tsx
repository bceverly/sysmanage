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

vi.mock('../../Services/imageMode', () => ({
    stageImage: vi.fn(),
    applyImage: vi.fn(),
    rollbackImage: vi.fn(),
}));

vi.mock('../../hooks/useModuleLicensed', () => ({
    __esModule: true,
    default: vi.fn(),
}));

import { stageImage, applyImage, rollbackImage } from '../../Services/imageMode';
import useModuleLicensed from '../../hooks/useModuleLicensed';
import HostImageModeTab from './HostImageModeTab';
import { SysManageHost } from '../../Services/hosts';

const mockStage = stageImage as unknown as ReturnType<typeof vi.fn>;
const mockApply = applyImage as unknown as ReturnType<typeof vi.fn>;
const mockRollback = rollbackImage as unknown as ReturnType<typeof vi.fn>;
const mockLicensed = useModuleLicensed as unknown as ReturnType<typeof vi.fn>;

const HOST: SysManageHost = {
    id: 'h1',
    active: true,
    fqdn: 'imagehost.example.com',
    ipv4: '10.0.0.1',
    ipv6: '',
    status: 'up',
    approval_status: 'approved',
    last_access: '',
    is_image_mode: true,
    image_backend: 'bootc',
    booted_image_ref: 'quay.io/fedora/fedora-bootc:41',
    booted_image_digest: 'sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
    rollback_available: true,
};

beforeEach(() => {
    vi.clearAllMocks();
    mockLicensed.mockReturnValue(true);
});

test('renders the booted image ref and truncated digest', () => {
    render(<HostImageModeTab host={HOST} />);
    expect(screen.getByText('quay.io/fedora/fedora-bootc:41')).toBeTruthy();
    // digest truncated to sha256: + first 12 hex chars
    expect(screen.getByText('sha256:abcdef012345')).toBeTruthy();
});

test('Stage calls stageImage', async () => {
    mockStage.mockResolvedValue({ result: true, action: 'stage', message_id: 'm1' });
    render(<HostImageModeTab host={HOST} />);
    fireEvent.click(screen.getByText('Stage'));
    await waitFor(() => expect(mockStage).toHaveBeenCalledWith('h1'));
});

test('Apply shows a reboot confirmation then calls applyImage', async () => {
    mockApply.mockResolvedValue({ result: true, action: 'apply', message_id: 'm2' });
    render(<HostImageModeTab host={HOST} />);
    // Clicking Apply should NOT dispatch immediately — a confirm dialog opens.
    fireEvent.click(screen.getByText('Apply'));
    expect(mockApply).not.toHaveBeenCalled();
    expect(screen.getByText('Apply staged image?')).toBeTruthy();
    fireEvent.click(screen.getByText('Confirm'));
    await waitFor(() => expect(mockApply).toHaveBeenCalledWith('h1'));
});

test('Rollback shows a reboot confirmation then calls rollbackImage', async () => {
    mockRollback.mockResolvedValue({ result: true, action: 'rollback', message_id: 'm3' });
    render(<HostImageModeTab host={HOST} />);
    fireEvent.click(screen.getByText('Rollback'));
    expect(mockRollback).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Confirm'));
    await waitFor(() => expect(mockRollback).toHaveBeenCalledWith('h1'));
});

const isDisabled = (label: string): boolean =>
    Boolean(screen.getByText(label).closest('button')?.hasAttribute('disabled'));

test('action buttons are disabled when the module is not licensed', () => {
    mockLicensed.mockReturnValue(false);
    render(<HostImageModeTab host={HOST} />);
    expect(isDisabled('Stage')).toBe(true);
    expect(isDisabled('Apply')).toBe(true);
    expect(isDisabled('Rollback')).toBe(true);
});

test('Rollback is disabled when rollback is not available', () => {
    render(<HostImageModeTab host={{ ...HOST, rollback_available: false }} />);
    expect(isDisabled('Rollback')).toBe(true);
});

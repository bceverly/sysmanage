// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Package manager needs repair (2026-11-13): flagged in the hosts grid, and
// "Repair Package Manager" for the checked hosts.

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { TFunction } from 'i18next';
import type { GridRenderCellParams } from '@mui/x-data-grid';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, fallback?: string | object) =>
    (typeof fallback === 'string' ? fallback : _k) }),
}));

import { buildHostColumns } from '../../Components/hostsColumns';
import HostsActionBar from '../../Components/HostsActionBar';
import type { SysManageHost } from '../../Services/hosts';

const t = ((key: string, fallback?: string | object) =>
  (typeof fallback === 'string' ? fallback : key)) as unknown as TFunction;

const statusCell = (row: Partial<SysManageHost>) => {
  const columns = buildHostColumns({
    t, navigate: vi.fn(), canViewHostDetails: true, tableData: [], hasHealthData: false,
  } as unknown as Parameters<typeof buildHostColumns>[0]);
  const status = columns.find(c => c.field === 'status')!;
  return render(<>{status.renderCell?.({ row, value: row.status } as unknown as GridRenderCellParams)}</>);
};

const bar = (over: Record<string, unknown> = {}) => {
  const props = {
    canApproveHosts: false, canDeployAntivirus: false, canRebootHost: false, canShutdownHost: false,
    canUpdateAgent: false, canDeleteHost: false, selectionCount: 1, hasPendingSelection: false,
    hasActivePrivilegedSelection: false, onApprove: vi.fn(), onRefreshData: vi.fn(),
    onBroadcastRefresh: vi.fn(), onGetDiagnostics: vi.fn(), onDeployOpenTelemetry: vi.fn(),
    onDeployAntivirus: vi.fn(), onRebootSelected: vi.fn(), onShutdownSelected: vi.fn(),
    onUpdateAgentSelected: vi.fn(), onDelete: vi.fn(), ...over,
  };
  return render(<HostsActionBar {...props} />);
};

describe('Package manager needs repair', () => {
  it('flags the host in the grid, with the package manager\'s own words on hover', () => {
    statusCell({ id: '1', status: 'up', last_access: new Date().toISOString(),
      package_manager_needs_repair: true, package_manager_repair_reason: 'dpkg was interrupted' } as Partial<SysManageHost>);
    expect(screen.getByTestId('package-manager-needs-repair')).toHaveTextContent('Package manager needs repair');
  });

  it('is not flagged otherwise', () => {
    statusCell({ id: '1', status: 'up', last_access: new Date().toISOString() } as Partial<SysManageHost>);
    expect(screen.queryByTestId('package-manager-needs-repair')).toBeNull();
  });

  it('offers Repair Package Manager while a checked host needs it, to whoever may apply updates', () => {
    const onRepair = vi.fn();
    bar({ canRepairPackageManager: true, hasRepairSelection: true, onRepairPackageManager: onRepair });
    fireEvent.click(screen.getByRole('button', { name: /Repair Package Manager/ }));
    expect(onRepair).toHaveBeenCalled();
  });

  it('is not offered without the role', () => {
    bar({ canRepairPackageManager: false, hasRepairSelection: true, onRepairPackageManager: vi.fn() });
    expect(screen.queryByRole('button', { name: /Repair Package Manager/ })).toBeNull();
  });
});

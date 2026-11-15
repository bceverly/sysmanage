// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Agent lost during its own upgrade (2026-11-15): the hosts grid says so
// instead of a bare "down", and the host page shows the hand repair.

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { TFunction } from 'i18next';
import type { GridRenderCellParams } from '@mui/x-data-grid';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, fallback?: string | object) =>
    (typeof fallback === 'string' ? fallback : _k) }),
}));

import { buildHostColumns } from '../../Components/hostsColumns';
import AgentLostInSelfUpdateAlert, { repairCommands } from '../../Components/HostDetail/AgentLostInSelfUpdateAlert';
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

const HOUR_AGO = new Date(Date.now() - 3600_000).toISOString();

const lostHost = (manager: string | null) => ({
  id: '1', fqdn: 'web1.lab', status: 'down', last_access: HOUR_AGO,
  agent_lost_in_self_update: true,
  agent_self_update_dispatched_at: '2026-11-15T09:00:00+00:00',
  agent_self_update_package_manager: manager,
}) as unknown as SysManageHost;

describe('Agent lost during its own upgrade: hosts grid', () => {
  it('labels the host instead of a bare Down', () => {
    statusCell(lostHost('apt'));
    expect(screen.getByTestId('lost-in-agent-upgrade')).toHaveTextContent('Lost during agent upgrade');
    expect(screen.queryByText('Down')).toBeNull();
  });

  it('shows the plain status otherwise', () => {
    statusCell({ id: '1', status: 'down', last_access: HOUR_AGO } as Partial<SysManageHost>);
    expect(screen.queryByTestId('lost-in-agent-upgrade')).toBeNull();
  });
});

describe('Agent lost during its own upgrade: host page', () => {
  it('explains what happened and gives the apt repair', () => {
    render(<AgentLostInSelfUpdateAlert host={lostHost('apt')} />);
    expect(screen.getByTestId('agent-lost-in-self-update')).toHaveTextContent('Agent lost during its own upgrade');
    const commands = screen.getByTestId('agent-lost-commands').textContent ?? '';
    expect(commands.split('\n')).toEqual([
      'sudo dpkg --configure -a',
      'sudo apt-get install -f -y',
      'sudo apt-get install --only-upgrade -y sysmanage-agent',
      'sudo systemctl start sysmanage-agent',
    ]);
  });

  it('gives the RPM repairs for dnf, yum and zypper', () => {
    expect(repairCommands('dnf')).toContain('sudo dnf upgrade -y sysmanage-agent');
    expect(repairCommands('yum')).toContain('sudo yum reinstall -y sysmanage-agent');
    expect(repairCommands('zypper')).toContain('sudo zypper --non-interactive install --force sysmanage-agent');
    expect(repairCommands('ZYPPER')?.at(-1)).toBe('sudo systemctl start sysmanage-agent');
  });

  it('falls back to plain instructions on other platforms', () => {
    render(<AgentLostInSelfUpdateAlert host={lostHost('winget')} />);
    expect(screen.queryByTestId('agent-lost-commands')).toBeNull();
    expect(screen.getByTestId('agent-lost-in-self-update')).toHaveTextContent('reinstall the agent package');
    expect(repairCommands(null)).toBeNull();
  });

  it('shows nothing for a host that was not lost', () => {
    const { container } = render(<AgentLostInSelfUpdateAlert host={{ ...lostHost('apt'), agent_lost_in_self_update: false }} />);
    expect(container).toBeEmptyDOMElement();
    render(<AgentLostInSelfUpdateAlert host={null} />);
    expect(screen.queryByTestId('agent-lost-in-self-update')).toBeNull();
  });
});

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * A Pro+ engine refused at startup stays off until the server restarts, even
 * once the migrations have run.  Written after 2026-11-04: prod was migrated
 * after a restart, the banner went on saying "migrate", and the backup engine
 * stayed unloaded for a day.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MigrationCompatBanner from '../../Components/MigrationCompatBanner';
import api from '../../Services/api';

vi.mock('react-i18next', () => {
  const t = (key: string, opts?: unknown) => (typeof opts === 'string' ? opts : key);
  return { useTranslation: () => ({ t }) };
});

vi.mock('../../Services/api', () => ({ default: { get: vi.fn() } }));

const get = api.get as unknown as ReturnType<typeof vi.fn>;

function answer(kind: string) {
  get.mockResolvedValue({
    data: {
      incompatibilities: [
        {
          module_code: 'backup_engine',
          required_revision: 'q77ossbackupkeys',
          current_revision: kind === 'restart_needed' ? 'q79cloudnodelete' : 'q75backuptagpolicy',
          kind,
        },
      ],
      pending_updates: [],
    },
  });
}

describe('MigrationCompatBanner', () => {
  beforeEach(() => {
    get.mockReset();
    localStorage.setItem('bearer_token', 'token');
  });

  it('asks for the migrations while they are pending', async () => {
    answer('migration_pending');
    render(<MigrationCompatBanner />);
    expect(await screen.findByText('Database migration required')).toBeInTheDocument();
    expect(screen.queryByText('Restart SysManage to load Pro+ engines')).toBeNull();
  });

  it('asks for a restart once the database has been migrated', async () => {
    answer('restart_needed');
    render(<MigrationCompatBanner />);
    expect(await screen.findByText('Restart SysManage to load Pro+ engines')).toBeInTheDocument();
    expect(screen.getByText('backup_engine')).toBeInTheDocument();
    expect(screen.queryByText('Database migration required')).toBeNull();
  });
});

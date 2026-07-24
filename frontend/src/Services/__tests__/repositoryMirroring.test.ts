// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Unit tests for the repository mirroring API service.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import axiosInstance from '../api';
import {
  listMirrors,
  createMirror,
  updateMirror,
  deleteMirror,
  syncMirror,
  snapshotMirror,
  restoreMirror,
  listSnapshots,
  getMirrorSettings,
  updateMirrorSettings,
  listPlatformConfigs,
  createPlatformConfig,
  updatePlatformConfig,
  deletePlatformConfig,
  listKnownVersions,
  listDefaultMirrorAssignments,
  setDefaultMirrorAssignment,
  getMirrorSetupStatus,
  refreshMirrorSetupStatus,
  installMirrorTools,
  listTrackedSnaps,
  trackSnap,
  untrackSnap,
  captureSnaps,
  type MirrorRepositoryCreate,
  type MirrorPlatformConfigPayload,
} from '../repositoryMirroring';

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const ok = (data: unknown) => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  config: {} as any,
});

describe('repositoryMirroring service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listMirrors', () => {
    it('GETs the mirror-repositories list and returns data', async () => {
      const mirrors = [{ id: 'm1', name: 'main' }];
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(ok(mirrors));

      const result = await listMirrors();

      expect(result).toEqual(mirrors);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/mirror-repositories');
    });

    it('propagates errors', async () => {
      vi.mocked(axiosInstance.get).mockRejectedValueOnce(new Error('boom'));
      await expect(listMirrors()).rejects.toThrow('boom');
    });
  });

  describe('createMirror', () => {
    it('POSTs the payload and returns the created mirror', async () => {
      const payload: MirrorRepositoryCreate = {
        name: 'main',
        package_manager: 'apt',
        upstream_url: 'http://deb',
        host_id: 'h1',
      };
      const created = { id: 'm1', ...payload };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(ok(created));

      const result = await createMirror(payload);

      expect(result).toEqual(created);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories',
        payload,
      );
    });

    it('propagates errors', async () => {
      vi.mocked(axiosInstance.post).mockRejectedValueOnce(new Error('402'));
      await expect(
        createMirror({
          name: 'x',
          package_manager: 'apt',
          upstream_url: 'u',
          host_id: 'h',
        }),
      ).rejects.toThrow('402');
    });
  });

  describe('updateMirror', () => {
    it('PUTs to the id-scoped URL with the patch', async () => {
      const patch = { enabled: false };
      const updated = { id: 'm1', enabled: false };
      vi.mocked(axiosInstance.put).mockResolvedValueOnce(ok(updated));

      const result = await updateMirror('m1', patch);

      expect(result).toEqual(updated);
      expect(axiosInstance.put).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1',
        patch,
      );
    });

    it('rejects invalid identifiers before calling axios', async () => {
      await expect(updateMirror('bad/id', {})).rejects.toThrow(
        'Invalid identifier: bad/id',
      );
      expect(axiosInstance.put).not.toHaveBeenCalled();
    });
  });

  describe('deleteMirror', () => {
    it('DELETEs the id-scoped URL', async () => {
      vi.mocked(axiosInstance.delete).mockResolvedValueOnce(ok(undefined));

      await deleteMirror('m1');

      expect(axiosInstance.delete).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1',
      );
    });

    it('rejects invalid identifiers', async () => {
      await expect(deleteMirror('a b')).rejects.toThrow('Invalid identifier: a b');
      expect(axiosInstance.delete).not.toHaveBeenCalled();
    });
  });

  describe('syncMirror', () => {
    it('POSTs to the sync endpoint and returns data', async () => {
      const resp = { message: 'queued', mirror_id: 'm1', message_id: 'msg1' };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(ok(resp));

      const result = await syncMirror('m1');

      expect(result).toEqual(resp);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1/sync',
      );
    });

    it('rejects invalid identifiers', async () => {
      await expect(syncMirror('..')).rejects.toThrow('Invalid identifier: ..');
    });
  });

  describe('snapshotMirror', () => {
    it('POSTs to the snapshot endpoint and returns data', async () => {
      const resp = { snapshot_id: 's1', message_id: 'msg1' };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(ok(resp));

      const result = await snapshotMirror('m1');

      expect(result).toEqual(resp);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1/snapshot',
      );
    });
  });

  describe('restoreMirror', () => {
    it('POSTs to the restore endpoint with both ids', async () => {
      const resp = { snapshot_id: 's1', message_id: 'msg1' };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(ok(resp));

      const result = await restoreMirror('m1', 's1');

      expect(result).toEqual(resp);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1/restore/s1',
      );
    });

    it('validates both ids', async () => {
      await expect(restoreMirror('m1', 'bad/snap')).rejects.toThrow(
        'Invalid identifier: bad/snap',
      );
    });
  });

  describe('listSnapshots', () => {
    it('GETs the snapshots endpoint', async () => {
      const snaps = [{ id: 's1' }];
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(ok(snaps));

      const result = await listSnapshots('m1');

      expect(result).toEqual(snaps);
      expect(axiosInstance.get).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1/snapshots',
      );
    });
  });

  describe('getMirrorSettings', () => {
    it('GETs the settings endpoint', async () => {
      const settings = { mirror_root_path: '/srv' };
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(ok(settings));

      const result = await getMirrorSettings();

      expect(result).toEqual(settings);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/settings/mirror');
    });
  });

  describe('updateMirrorSettings', () => {
    it('PUTs the settings patch', async () => {
      const patch = { retention_window_days: 30 };
      const updated = { mirror_root_path: '/srv', retention_window_days: 30 };
      vi.mocked(axiosInstance.put).mockResolvedValueOnce(ok(updated));

      const result = await updateMirrorSettings(patch);

      expect(result).toEqual(updated);
      expect(axiosInstance.put).toHaveBeenCalledWith('/api/v1/settings/mirror', patch);
    });
  });

  describe('listPlatformConfigs', () => {
    it('GETs the platform-configs endpoint', async () => {
      const configs = [{ id: 'c1', platform: 'apt' }];
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(ok(configs));

      const result = await listPlatformConfigs();

      expect(result).toEqual(configs);
      expect(axiosInstance.get).toHaveBeenCalledWith(
        '/api/v1/mirror-platform-configs',
      );
    });
  });

  describe('createPlatformConfig', () => {
    it('POSTs the platform config payload', async () => {
      const payload: MirrorPlatformConfigPayload = {
        platform: 'apt',
        host_id: 'h1',
      };
      const created = { id: 'c1', ...payload };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(ok(created));

      const result = await createPlatformConfig(payload);

      expect(result).toEqual(created);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/mirror-platform-configs',
        payload,
      );
    });
  });

  describe('updatePlatformConfig', () => {
    it('PUTs to the id-scoped platform config URL', async () => {
      const payload: MirrorPlatformConfigPayload = {
        platform: 'dnf',
        host_id: 'h1',
      };
      const updated = { id: 'c1', ...payload };
      vi.mocked(axiosInstance.put).mockResolvedValueOnce(ok(updated));

      const result = await updatePlatformConfig('c1', payload);

      expect(result).toEqual(updated);
      expect(axiosInstance.put).toHaveBeenCalledWith(
        '/api/v1/mirror-platform-configs/c1',
        payload,
      );
    });

    it('rejects invalid identifiers', async () => {
      await expect(
        updatePlatformConfig('c@1', { platform: 'apt', host_id: 'h' }),
      ).rejects.toThrow('Invalid identifier: c@1');
    });
  });

  describe('deletePlatformConfig', () => {
    it('DELETEs the id-scoped platform config URL', async () => {
      vi.mocked(axiosInstance.delete).mockResolvedValueOnce(ok(undefined));

      await deletePlatformConfig('c1');

      expect(axiosInstance.delete).toHaveBeenCalledWith(
        '/api/v1/mirror-platform-configs/c1',
      );
    });
  });

  describe('listKnownVersions', () => {
    it('GETs with an empty params object when no platform is given', async () => {
      const versions = [{ id: 'v1' }];
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(ok(versions));

      const result = await listKnownVersions();

      expect(result).toEqual(versions);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/mirror-known-versions', {
        params: {},
      });
    });

    it('GETs with a platform param when provided', async () => {
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(ok([]));

      await listKnownVersions('dnf');

      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/mirror-known-versions', {
        params: { platform: 'dnf' },
      });
    });
  });

  describe('listDefaultMirrorAssignments', () => {
    it('GETs the host-defaults mirrors endpoint', async () => {
      const rows = [{ platform: 'apt', version_key: 'noble' }];
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(ok(rows));

      const result = await listDefaultMirrorAssignments();

      expect(result).toEqual(rows);
      expect(axiosInstance.get).toHaveBeenCalledWith('/api/v1/host-defaults/mirrors');
    });
  });

  describe('setDefaultMirrorAssignment', () => {
    it('PUTs with an encoded version key and mirror_id body', async () => {
      const resp = {
        platform: 'apt',
        version_key: 'ubuntu 24',
        os_family: 'debian',
        mirror_id: 'm1',
        previous_mirror_id: null,
        dispatched: [],
      };
      vi.mocked(axiosInstance.put).mockResolvedValueOnce(ok(resp));

      const result = await setDefaultMirrorAssignment(
        'apt',
        'ubuntu 24',
        'debian',
        'm1',
      );

      expect(result).toEqual(resp);
      expect(axiosInstance.put).toHaveBeenCalledWith(
        '/api/v1/host-defaults/mirrors/apt/ubuntu%2024/debian',
        { mirror_id: 'm1' },
      );
    });

    it('passes a null mirror_id through', async () => {
      vi.mocked(axiosInstance.put).mockResolvedValueOnce(ok({}));

      await setDefaultMirrorAssignment('dnf', 'el9', 'rhel', null);

      expect(axiosInstance.put).toHaveBeenCalledWith(
        '/api/v1/host-defaults/mirrors/dnf/el9/rhel',
        { mirror_id: null },
      );
    });
  });

  describe('getMirrorSetupStatus', () => {
    it('GETs the setup-status endpoint for a host', async () => {
      const status = { host_id: 'h1', tools: {} };
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(ok(status));

      const result = await getMirrorSetupStatus('h1');

      expect(result).toEqual(status);
      expect(axiosInstance.get).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/setup-status/h1',
      );
    });

    it('rejects invalid host ids', async () => {
      await expect(getMirrorSetupStatus('h/1')).rejects.toThrow(
        'Invalid identifier: h/1',
      );
    });
  });

  describe('refreshMirrorSetupStatus', () => {
    it('POSTs to the setup-status refresh endpoint', async () => {
      const resp = { host_id: 'h1', message_id: 'msg1', status: 'dispatched' };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(ok(resp));

      const result = await refreshMirrorSetupStatus('h1');

      expect(result).toEqual(resp);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/setup-status/h1/refresh',
      );
    });
  });

  describe('installMirrorTools', () => {
    it('POSTs to setup-install with the package_manager body', async () => {
      const resp = {
        host_id: 'h1',
        message_id: 'msg1',
        package_manager: 'apt',
        status: 'dispatched',
      };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(ok(resp));

      const result = await installMirrorTools('h1', 'apt');

      expect(result).toEqual(resp);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/setup-install/h1',
        { package_manager: 'apt' },
      );
    });

    it('rejects invalid host ids', async () => {
      await expect(installMirrorTools('h!1', 'dnf')).rejects.toThrow(
        'Invalid identifier: h!1',
      );
    });
  });

  describe('snap store proxy', () => {
    it('listTrackedSnaps GETs the id-scoped /snaps URL', async () => {
      const rows = [{ id: 's1', snap_name: 'hello', capture_status: 'TRACKED' }];
      vi.mocked(axiosInstance.get).mockResolvedValueOnce(ok(rows));
      const result = await listTrackedSnaps('m1');
      expect(result).toEqual(rows);
      expect(axiosInstance.get).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1/snaps',
      );
    });

    it('trackSnap POSTs the {snap_name, channel} body', async () => {
      const created = { id: 's1', snap_name: 'hello', channel: 'latest/edge' };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(ok(created));
      const result = await trackSnap('m1', {
        snap_name: 'hello',
        channel: 'latest/edge',
      });
      expect(result).toEqual(created);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1/snaps',
        { snap_name: 'hello', channel: 'latest/edge' },
      );
    });

    it('untrackSnap DELETEs the id + snap-content-id URL', async () => {
      vi.mocked(axiosInstance.delete).mockResolvedValueOnce(ok(undefined));
      await untrackSnap('m1', 's1');
      expect(axiosInstance.delete).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1/snaps/s1',
      );
    });

    it('captureSnaps POSTs to /capture-snaps and returns data', async () => {
      const resp = { message: 'ok', mirror_id: 'm1', message_id: 'x', snap_count: 2 };
      vi.mocked(axiosInstance.post).mockResolvedValueOnce(ok(resp));
      const result = await captureSnaps('m1');
      expect(result).toEqual(resp);
      expect(axiosInstance.post).toHaveBeenCalledWith(
        '/api/v1/mirror-repositories/m1/capture-snaps',
      );
    });

    it('rejects invalid identifiers before calling axios', async () => {
      await expect(listTrackedSnaps('a b')).rejects.toThrow('Invalid identifier');
      await expect(untrackSnap('m1', 'a b')).rejects.toThrow('Invalid identifier');
    });
  });
});

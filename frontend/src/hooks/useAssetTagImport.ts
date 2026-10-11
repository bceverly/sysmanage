// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// State for asset-tag CSV import / export and held tags (Phase 23.2 S5).
// Choosing a file runs the server's dry run at once; Apply sends the SAME
// text again and the server re-plans it, so nothing the preview showed is
// trusted on the way back.

import { useCallback, useEffect, useState } from 'react';
import {
  HeldTag,
  ImportResult,
  applyAssetTagImport,
  errorCode,
  exportAssetTags,
  getHeldTags,
  previewAssetTagImport,
  releaseHeldTag,
} from '../Services/machines';
import { hasPermission, SecurityRoles } from '../Services/permissions';

/** What happened last, for the page's one status line. */
export type ImportNotice =
  | { kind: 'applied'; result: ImportResult }
  | { kind: 'fileError'; code: string | null }
  | { kind: 'failed' }
  | null;

export interface AssetTagImportState {
  canManage: boolean;
  fileName: string | null;
  preview: ImportResult | null;
  busy: boolean;
  notice: ImportNotice;
  held: HeldTag[];
  heldFailed: boolean;
  chooseFile: (file: { name: string; text: () => Promise<string> } | undefined) => void;
  apply: () => Promise<void>;
  reset: () => void;
  download: () => Promise<void>;
  release: (id: string) => Promise<void>;
}

/** Rows an apply would write. */
export const writableCount = (preview: ImportResult | null): number =>
  (preview?.summary.assign ?? 0) + (preview?.summary.hold ?? 0);

const saveBlob = (blob: Blob, name: string): void => {
  const url = globalThis.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  globalThis.URL.revokeObjectURL(url);
};

export const useAssetTagImport = (): AssetTagImportState => {
  const [canManage, setCanManage] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<ImportNotice>(null);
  const [held, setHeld] = useState<HeldTag[]>([]);
  const [heldFailed, setHeldFailed] = useState(false);

  const loadHeld = useCallback(async () => {
    try {
      setHeld(await getHeldTags());
      setHeldFailed(false);
    } catch (error) {
      console.error('Failed to load held asset tags:', error);
      setHeldFailed(true);
    }
  }, []);

  useEffect(() => {
    hasPermission(SecurityRoles.MANAGE_ASSET_TAGS)
      .then(setCanManage)
      .catch(() => setCanManage(false));
    void loadHeld();
  }, [loadHeld]);

  const runPreview = useCallback(async (csv: string) => {
    setBusy(true);
    try {
      setPreview(await previewAssetTagImport(csv));
    } catch (error) {
      setPreview(null);
      setNotice({ kind: 'fileError', code: errorCode(error) });
    } finally {
      setBusy(false);
    }
  }, []);

  const chooseFile: AssetTagImportState['chooseFile'] = file => {
    if (!file) return;
    setNotice(null);
    setFileName(file.name);
    file
      .text()
      .then(csv => {
        setText(csv);
        return runPreview(csv);
      })
      .catch(() => setNotice({ kind: 'fileError', code: null }));
  };

  const reset = () => {
    setFileName(null);
    setText(null);
    setPreview(null);
  };

  const apply = async () => {
    if (text === null) return;
    setBusy(true);
    try {
      const result = await applyAssetTagImport(text);
      setNotice({ kind: 'applied', result });
      reset();
      await loadHeld();
    } catch (error) {
      console.error('Asset tag import failed:', error);
      setNotice({ kind: 'failed' });
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    try {
      saveBlob(await exportAssetTags(), `asset_tags_${new Date().toISOString().slice(0, 10)}.csv`);
    } catch (error) {
      console.error('Asset tag export failed:', error);
      setNotice({ kind: 'failed' });
    }
  };

  const release = async (id: string) => {
    try {
      await releaseHeldTag(id);
    } catch (error) {
      console.error('Releasing a held asset tag failed:', error);
      setNotice({ kind: 'failed' });
    }
    await loadHeld();
  };

  return {
    canManage,
    fileName,
    preview,
    busy,
    notice,
    held,
    heldFailed,
    chooseFile,
    apply,
    reset,
    download,
    release,
  };
};

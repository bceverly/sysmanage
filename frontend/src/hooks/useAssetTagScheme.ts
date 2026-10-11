// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// State for the asset-tag naming-scheme editor (Phase 23.2).  Holds the saved
// report, the draft being edited, and a debounced live preview of the draft.
// A preview saves nothing; only save() writes.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AssetTagScheme,
  SchemeReport,
  errorCode,
  getAssetTagScheme,
  previewAssetTagScheme,
  saveAssetTagScheme,
} from '../Services/machines';
import { hasPermission, SecurityRoles } from '../Services/permissions';

export const PREVIEW_DEBOUNCE_MS = 300;

export type SaveOutcome = 'saved' | 'invalid' | 'failed';

/** The field names a 422 ``invalid_scheme`` refusal names, else none. */
export const invalidFieldsOf = (error: unknown): string[] => {
  if (errorCode(error) !== 'invalid_scheme') return [];
  const detail = (error as { response?: { data?: { detail?: { fields?: unknown } } } })
    .response?.data?.detail;
  const fields = detail?.fields;
  return Array.isArray(fields) ? fields.map(String) : [];
};

export interface AssetTagSchemeState {
  loading: boolean;
  loadFailed: boolean;
  canManage: boolean;
  draft: AssetTagScheme | null;
  saved: SchemeReport | null;
  preview: SchemeReport | null;
  previewing: boolean;
  previewFailed: boolean;
  saving: boolean;
  invalidFields: string[];
  update: (changes: Partial<AssetTagScheme>) => void;
  save: () => Promise<SaveOutcome>;
}

const useLoad = (onLoaded: (report: SchemeReport) => void) => {
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [canManage, setCanManage] = useState(false);
  const [saved, setSaved] = useState<SchemeReport | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const [report, allowed] = await Promise.all([
        getAssetTagScheme().catch(() => null),
        hasPermission(SecurityRoles.MANAGE_ASSET_TAGS).catch(() => false),
      ]);
      if (!alive) return;
      setSaved(report);
      if (report) onLoaded(report);
      setLoadFailed(report === null);
      setCanManage(allowed);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [onLoaded]);

  return { loading, loadFailed, canManage, saved, setSaved };
};

export const useAssetTagScheme = (): AssetTagSchemeState => {
  const [draft, setDraftState] = useState<AssetTagScheme | null>(null);
  // Mirrors ``draft`` so update() can build the next draft without doing its
  // scheduling inside a state updater (updaters must stay pure).
  const draftRef = useRef<AssetTagScheme | null>(null);
  const setDraft = useCallback((next: AssetTagScheme | null) => {
    draftRef.current = next;
    setDraftState(next);
  }, []);
  const [preview, setPreview] = useState<SchemeReport | null>(null);
  const onLoaded = useCallback(
    (report: SchemeReport) => {
      setDraft(report.scheme);
      setPreview(report);
    },
    [setDraft],
  );
  const { loading, loadFailed, canManage, saved, setSaved } = useLoad(onLoaded);
  const [previewing, setPreviewing] = useState(false);
  const [previewFailed, setPreviewFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [invalidFields, setInvalidFields] = useState<string[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Only the newest preview request may land; older answers are stale.
  const sequence = useRef(0);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const runPreview = useCallback(async (scheme: AssetTagScheme) => {
    const mine = ++sequence.current;
    try {
      const report = await previewAssetTagScheme(scheme);
      if (mine !== sequence.current) return;
      setPreview(report);
      setPreviewFailed(false);
      setInvalidFields([]);
    } catch (error) {
      if (mine !== sequence.current) return;
      setPreviewFailed(true);
      setInvalidFields(invalidFieldsOf(error));
    } finally {
      if (mine === sequence.current) setPreviewing(false);
    }
  }, []);

  const update = useCallback(
    (changes: Partial<AssetTagScheme>) => {
      const prev = draftRef.current;
      if (prev === null) return;
      const next = { ...prev, ...changes };
      setDraft(next);
      if (timer.current) clearTimeout(timer.current);
      setPreviewing(true);
      timer.current = setTimeout(() => {
        timer.current = null;
        void runPreview(next);
      }, PREVIEW_DEBOUNCE_MS);
      const touched = Object.keys(changes);
      setInvalidFields(current => current.filter(f => !touched.includes(f)));
    },
    [runPreview, setDraft],
  );

  const save = useCallback(async (): Promise<SaveOutcome> => {
    if (draft === null) return 'failed';
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    sequence.current += 1;
    setPreviewing(false);
    setSaving(true);
    try {
      const report = await saveAssetTagScheme(draft);
      setSaved(report);
      setDraft(report.scheme);
      setPreview(report);
      setPreviewFailed(false);
      setInvalidFields([]);
      return 'saved';
    } catch (error) {
      const fields = invalidFieldsOf(error);
      setInvalidFields(fields);
      return fields.length > 0 || errorCode(error) === 'invalid_scheme' ? 'invalid' : 'failed';
    } finally {
      setSaving(false);
    }
  }, [draft, setSaved, setDraft]);

  return {
    loading,
    loadFailed,
    canManage,
    draft,
    saved,
    preview,
    previewing,
    previewFailed,
    saving,
    invalidFields,
    update,
    save,
  };
};

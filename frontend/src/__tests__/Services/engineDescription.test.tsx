/**
 * Tests for the engine plan-description resolver (Phase 11 B7).
 */

import { resolveCommandDescription } from '../../Services/engineDescription';
import type { TFunction } from 'i18next';

describe('resolveCommandDescription', () => {
  // Stub TFunction: returns the key with params interpolated when the key
  // is in our fake catalog; otherwise returns the key verbatim (i18next's
  // default missing-key behavior).
  const catalog: Record<string, string> = {
    'engine.airgap_collector.cmd.mirror_repo':
      'Mirroring {{distro}} {{version}} repo {{repo}}',
    'engine.foo.bar': 'Doing the foo',
  };
  const t: TFunction = ((key: string, paramsOrFallback?: unknown) => {
    const tpl = catalog[key];
    if (tpl) {
      const params = (paramsOrFallback as Record<string, unknown>) || {};
      return tpl.replace(/{{(\w+)}}/g, (_m, n) => String(params[n] ?? ''));
    }
    // Missing-key path — i18next would return the key verbatim
    return key;
  }) as TFunction;

  it('returns the localized form when key is present in catalog', () => {
    const out = resolveCommandDescription(
      {
        description: 'mirror fedora 40 repo updates',
        description_key: 'engine.airgap_collector.cmd.mirror_repo',
        description_params: {
          distro: 'fedora',
          version: '40',
          repo: 'updates',
        },
      },
      t,
    );
    expect(out).toBe('Mirroring fedora 40 repo updates');
  });

  it('falls back to description when key is missing from catalog', () => {
    const out = resolveCommandDescription(
      {
        description: 'mirror unknown 99 repo legacy',
        description_key: 'engine.unknown_engine.cmd.thing',
        description_params: { x: 'y' },
      },
      t,
    );
    expect(out).toBe('mirror unknown 99 repo legacy');
  });

  it('falls back to description when no key is set', () => {
    const out = resolveCommandDescription(
      { description: 'legacy engine without envelope' },
      t,
    );
    expect(out).toBe('legacy engine without envelope');
  });

  it('returns empty string when both fields are absent', () => {
    expect(resolveCommandDescription({}, t)).toBe('');
  });

  it('returns empty string for null/undefined input', () => {
    expect(resolveCommandDescription(null, t)).toBe('');
    expect(resolveCommandDescription(undefined, t)).toBe('');
  });

  it('handles description_key without description_params', () => {
    const out = resolveCommandDescription(
      {
        description: 'doing the foo',
        description_key: 'engine.foo.bar',
      },
      t,
    );
    expect(out).toBe('Doing the foo');
  });
});

/**
 * Engine plan-description resolver (Phase 11 B7).
 *
 * Pro+ engines emit plan commands with both a legacy English
 * ``description`` field and a ``{description_key, description_params}``
 * envelope.  This helper resolves the right thing to render:
 *
 *   - When ``description_key`` is present AND the locale catalog has
 *     it, return ``t(description_key, description_params)`` — the
 *     localized form.
 *   - When ``description_key`` is missing OR the catalog doesn't have
 *     the key (older engine, partial migration), fall back to
 *     ``description`` verbatim.
 *
 * The fallback path is critical for incremental rollout: each Pro+
 * engine adopts the envelope when next touched, so frontend rendering
 * works for both migrated and un-migrated engines simultaneously.
 *
 * Use sites are anywhere a plan-command result's description gets
 * shown to an operator — execution logs, audit trails, plan-preview
 * dialogs, etc.  When such a UI surface is added, route it through
 * ``resolveCommandDescription``.
 */

import type { TFunction } from 'i18next';

/**
 * The minimum shape we care about — every plan-command result dict
 * has at least ``description``; envelope-aware engines also emit
 * ``description_key`` and ``description_params``.
 */
export interface PlanCommandResultLike {
  description?: string;
  description_key?: string;
  description_params?: Record<string, string | number | boolean | null>;
}

/**
 * Return the operator-facing string for a plan command's description.
 *
 * Implements the resolver protocol documented in ROADMAP §11.7:
 *   1. If ``description_key`` is set AND ``t`` finds the key in the
 *      active locale, render the localized form.
 *   2. Otherwise, fall back to ``description`` (raw English from the
 *      engine — what we shipped pre-Phase-11-B7).
 *   3. If neither is set, return an empty string (some plan-builders
 *      emit purely-internal commands without descriptions).
 *
 * i18next's default behavior when a key is missing is to return the
 * key itself.  We detect that and fall back to ``description``.
 */
export function resolveCommandDescription(
  cmd: PlanCommandResultLike | null | undefined,
  t: TFunction,
): string {
  if (!cmd) {
    return '';
  }
  const key = cmd.description_key;
  if (key) {
    const params = cmd.description_params || {};
    const localized = t(key, params);
    // i18next returns the key verbatim when a translation is missing.
    // That's a fine fallback signal — drop through to ``description``.
    if (localized && localized !== key) {
      return localized;
    }
  }
  return cmd.description || '';
}

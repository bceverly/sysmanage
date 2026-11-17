// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Phones, tablets and cameras each have their own type (ROADMAP 26.10);
// "phone or tablet" stays for when nothing tells them apart.

import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import { categoryForType, deviceTypeLabel } from '../discoveryLabels';

const t = ((_key: string, fallback?: string) => fallback ?? _key) as unknown as TFunction;

describe('device types (26.10)', () => {
  it('labels the new types and keeps the either-or one', () => {
    expect(deviceTypeLabel(t, 'phone')).toBe('Phone');
    expect(deviceTypeLabel(t, 'tablet')).toBe('Tablet');
    expect(deviceTypeLabel(t, 'camera')).toBe('Camera');
    expect(deviceTypeLabel(t, 'phone_or_tablet')).toBe('Phone or tablet');
  });

  it('suggests the matching category when marking one as known', () => {
    expect(categoryForType('phone')).toBe('personal_device');
    expect(categoryForType('tablet')).toBe('personal_device');
    expect(categoryForType('camera')).toBe('iot');
  });
});

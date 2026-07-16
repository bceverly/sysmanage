// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

export { pluginManager } from './PluginManager';
export { PluginProvider, usePlugins } from './PluginContext';
export type {
    PluginRegistration,
    PluginNavItem,
    PluginRoute,
    PluginHostDetailTab,
    PluginSettingsTab,
    PluginTranslations,
    TabInsertPosition,
    SysManageShared,
} from './types';

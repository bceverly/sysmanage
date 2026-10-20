// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import type { TFunction } from "i18next";
import { t } from "../TimeSync/_i18nMock";
import { runStatusLabel as label } from "../../../Components/Backups/backupLabels";
import { sortHosts } from "../../../Components/Backups/BackupHostsTable";
import type { BackupHost, BackupRun } from "../../../Services/backups";

export const runStatusLabel = (run: BackupRun): string => label(t as unknown as TFunction, run);
export const sortHostsForTest = (rows: BackupHost[]): BackupHost[] => sortHosts(rows);

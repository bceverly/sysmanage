// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The host's Backup tab: the Community backup card and, below it, a licensed
// plugin's panel for the same tab (Pro+ backup_engine: encryption).

import React from "react";
import { Stack } from "@mui/material";
import HostBackupCard from "../Backups/HostBackupCard";

const HostBackupTab: React.FC<{
  hostId: string;
  extension?: React.ComponentType<{ hostId: string }>;
}> = ({ hostId, extension: Extension }) => (
  <Stack spacing={2}>
    <HostBackupCard hostId={hostId} />
    {Extension && <Extension hostId={hostId} />}
  </Stack>
);

export default HostBackupTab;

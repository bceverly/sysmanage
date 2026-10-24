// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The host's Automation tab: its config-management engines and the history of
// profile runs on it (Phase 20.1).  A licensed plugin that registers the
// ``automation`` host tab (Pro+ automation_engine: saved scripts, executions,
// approvals) is shown below them, in the same tab, as ``extension``.

import React from "react";
import { Grid } from "@mui/material";
import ConfigManagementEnginesCard from "../ConfigManagementEnginesCard";
import ConfigProfileRunHistory from "../ConfigProfileRunHistory";

interface HostAutomationTabProps {
  hostId: string;
  canInstall: boolean;
  isHostActive: boolean;
  isAgentPrivileged: boolean;
  extension?: React.ComponentType<{ hostId: string }>;
}

const HostAutomationTab: React.FC<HostAutomationTabProps> = ({
  hostId,
  canInstall,
  isHostActive,
  isAgentPrivileged,
  extension: Extension,
}) => {
  // Bumped when a profile is applied so the run-history panel re-reads instead
  // of leaving the operator staring at a stale list wondering if it took.
  const [configRunsRefresh, setConfigRunsRefresh] = React.useState(0);
  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 6 }} sx={{ display: "flex" }}>
        <ConfigManagementEnginesCard
          hostId={hostId}
          canInstall={canInstall}
          onProfileApplied={() => setConfigRunsRefresh((n) => n + 1)}
          isHostActive={isHostActive}
          isAgentPrivileged={isAgentPrivileged}
          sx={{ height: "100%", width: "100%" }}
        />
      </Grid>
      {/* Full width: it is a table, and squeezing it into a half column
          makes every row wrap. */}
      <Grid size={{ xs: 12 }}>
        <ConfigProfileRunHistory hostId={hostId} refreshTrigger={configRunsRefresh} />
      </Grid>
      {Extension && (
        <Grid size={{ xs: 12 }}>
          <Extension hostId={hostId} />
        </Grid>
      )}
    </Grid>
  );
};

export default HostAutomationTab;

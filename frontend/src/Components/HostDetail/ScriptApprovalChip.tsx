// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Scripts need approval": the host's agent runs only scripts approved
// through the Professional+ approval workflow (its
// script_execution.security.require_approval setting), and the server
// refuses one-off scripts to it.

import React from "react";
import { Chip, Tooltip } from "@mui/material";
import { useTranslation } from "react-i18next";

const ScriptApprovalChip: React.FC<{ required?: boolean }> = ({ required }) => {
  const { t } = useTranslation();
  if (!required) return null;
  return (
    <Tooltip
      title={t(
        "hosts.scriptsNeedApprovalTooltip",
        "This host's agent runs only scripts approved through the approval workflow (Professional+). One-off scripts are refused.",
      )}
    >
      <Chip
        size="small"
        color="warning"
        variant="outlined"
        sx={{ ml: 1 }}
        label={t("hosts.scriptsNeedApproval", "Scripts need approval")}
      />
    </Tooltip>
  );
};

export default ScriptApprovalChip;

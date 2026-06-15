/**
 * Navbar tenant switcher (Phase 13.1).
 *
 * Shows the active tenant as a chip and lets the user switch between the
 * tenants they're granted to.  Only rendered when multi-tenancy is enabled
 * (the parent gates on it).  Switching re-mints the JWT with the new
 * ``tenant_id`` and reloads so every view refetches under the new scope.
 */

import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import Chip from "@mui/material/Chip";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ListItemText from "@mui/material/ListItemText";
import Check from "@mui/icons-material/Check";
import BusinessIcon from "@mui/icons-material/Business";

import {
  accountsService,
  getActiveTenantId,
  TenantAccount,
} from "../Services/accounts";

const TenantSwitcher: React.FC = () => {
  const { t } = useTranslation();
  const [accounts, setAccounts] = useState<TenantAccount[]>([]);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [activeId, setActiveId] = useState<string | null>(getActiveTenantId());
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    let cancelled = false;
    accountsService
      .list()
      .then((list) => {
        if (!cancelled) setAccounts(list);
      })
      .catch(() => {
        // No grants / endpoint unavailable → render nothing useful.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const active = accounts.find((a) => a.tenant_id === activeId);
  // Show the tenant id (short) when we have an active tenant but its account
  // metadata hasn't loaded yet, so the chip is never blank.
  let label: string;
  if (active) {
    label = active.name;
  } else if (activeId) {
    label = `${activeId.slice(0, 8)}…`;
  } else {
    label = t("tenants.switcher.none", "No tenant");
  }

  const handleSwitch = async (tenantId: string | null) => {
    setAnchorEl(null);
    if (tenantId === activeId || switching) return;
    setSwitching(true);
    try {
      await accountsService.switch(tenantId);
      setActiveId(tenantId);
      // Reload so every view refetches under the new tenant scope.
      globalThis.location.reload();
    } catch {
      setSwitching(false);
    }
  };

  // The parent only mounts this when multi-tenancy is enabled, so always show
  // the chip — it's the visible signal that the server is multi-tenant, even
  // before the user has switched into a tenant.
  return (
    <>
      <Chip
        icon={<BusinessIcon />}
        label={label}
        size="small"
        onClick={(e) => setAnchorEl(e.currentTarget)}
        sx={{ mr: 1, maxWidth: 200 }}
        title={t("tenants.switcher.tooltip", "Active tenant — click to switch")}
        aria-label={t(
          "tenants.switcher.tooltip",
          "Active tenant — click to switch",
        )}
      />
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
      >
        {/* Return to server scope (clear the active tenant). */}
        <MenuItem selected={!activeId} onClick={() => handleSwitch(null)}>
          {activeId ? (
            <span style={{ width: 24, display: "inline-block" }} />
          ) : (
            <Check fontSize="small" sx={{ mr: 1 }} />
          )}
          <ListItemText primary={t("tenants.switcher.none", "No tenant")} />
        </MenuItem>
        {accounts.length === 0 && (
          <MenuItem disabled>
            {t("tenants.switcher.noAccounts", "No tenant grants")}
          </MenuItem>
        )}
        {accounts.map((a) => (
          <MenuItem
            key={a.tenant_id}
            selected={a.tenant_id === activeId}
            onClick={() => handleSwitch(a.tenant_id)}
          >
            {a.tenant_id === activeId ? (
              <Check fontSize="small" sx={{ mr: 1 }} />
            ) : (
              <span style={{ width: 24, display: "inline-block" }} />
            )}
            <ListItemText primary={a.name} secondary={a.role} />
          </MenuItem>
        ))}
      </Menu>
    </>
  );
};

export default TenantSwitcher;

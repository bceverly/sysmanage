/**
 * Phase 12.3: client for the federation controller API.
 *
 * Every endpoint here returns either a real payload (when the Pro+
 * ``federation_controller_engine`` is loaded on the coordinator) or
 * a uniform ``{licensed: false, ...}`` stub (OSS / Community / unlicensed
 * Enterprise).  The page-level callers must check ``licensed`` before
 * trusting the rest of the payload — see ``Pages/Sites.tsx`` for the
 * canonical pattern.
 */

import { useEffect, useState } from "react";

import axiosInstance from "./api";

// Wire-shape contracts.  These match the OSS stub responses in
// ``backend/api/proplus_routes.py`` and what the future Pro+ engine
// will produce for the same routes.

export interface FederationSiteSummary {
  id: string;
  name: string;
  location_label?: string | null;
  url: string;
  status: "pending" | "enrolled" | "suspended" | "removed";
  host_count: number;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  agent_version_min?: string | null;
  geo_latitude?: number | null;
  geo_longitude?: number | null;
  geo_country_code?: string | null;
}

/**
 * Envelope shape returned by every federation endpoint.  ``licensed``
 * is the OSS probe: ``false`` means "the engine isn't loaded; render
 * a Pro+ upsell instead of trying to use the data".  The frontend
 * should NEVER infer engine availability from any other field.
 */
export interface FederationListSitesResponse {
  licensed: boolean;
  sites?: FederationSiteSummary[];
}

/**
 * Detail-tier site representation.  Superset of the list-tier
 * summary; includes timestamps the Sites card doesn't need.
 */
export interface FederationSiteDetail extends FederationSiteSummary {
  enrolled_at?: string | null;
  enrollment_token_expires_at?: string | null;
  sync_interval_seconds?: number;
}

export interface FederationSiteDetailResponse {
  licensed: boolean;
  site?: FederationSiteDetail;
}

/** Sync-status detail surface for the per-site Connection card. */
export interface FederationSiteSyncStatus {
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  pending_queue_depth?: number;
}

export interface FederationSiteSyncStatusResponse {
  licensed: boolean;
  status?: FederationSiteSyncStatus;
}

/** Body for the operator's "Add Site" enrollment form. */
export interface FederationEnrollSiteRequest {
  name: string;
  url: string;
  location_label?: string | null;
  sync_interval_seconds?: number;
  token_ttl_hours?: number;
}

/**
 * Response from POST /sites.  Carries the plaintext enrollment
 * token EXACTLY ONCE — the UI must surface it to the operator on
 * the success screen because it cannot be retrieved afterwards.
 */
export interface FederationEnrollSiteResponse {
  licensed: boolean;
  site?: FederationSiteDetail;
  enrollment_token?: string;
  enrollment_token_expires_at?: string | null;
}

/** Acknowledgement envelope for lifecycle actions. */
export interface FederationActionResponse {
  licensed: boolean;
  site?: FederationSiteDetail;
}

// ---------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------

/**
 * Fetch the list of federation sites.  Returns the raw envelope so
 * callers can branch on ``licensed``.  Network errors propagate as
 * the usual axios rejection.
 */
export async function doListFederationSites(): Promise<FederationListSitesResponse> {
  const response = await axiosInstance.get<FederationListSitesResponse>(
    "/api/v1/federation/sites",
  );
  return response.data;
}

/**
 * Fetch one site by its UUID.  ``licensed=false`` means the Pro+
 * engine isn't loaded; ``site`` undefined means the engine IS
 * loaded but no row matched (caller should render a 404 state).
 */
export async function doGetFederationSite(
  siteId: string,
): Promise<FederationSiteDetailResponse> {
  const response = await axiosInstance.get<FederationSiteDetailResponse>(
    `/api/v1/federation/sites/${encodeURIComponent(siteId)}`,
  );
  return response.data;
}

/**
 * Begin an enrollment.  The plaintext ``enrollment_token`` in the
 * response is the one-time-only value an operator delivers to the
 * subordinate site server out-of-band; the dialog must surface it
 * + warn that it cannot be retrieved later.
 */
export async function doEnrollFederationSite(
  body: FederationEnrollSiteRequest,
): Promise<FederationEnrollSiteResponse> {
  const response = await axiosInstance.post<FederationEnrollSiteResponse>(
    "/api/v1/federation/sites",
    body,
  );
  return response.data;
}

export async function doSuspendFederationSite(
  siteId: string,
): Promise<FederationActionResponse> {
  const response = await axiosInstance.post<FederationActionResponse>(
    `/api/v1/federation/sites/${encodeURIComponent(siteId)}/suspend`,
  );
  return response.data;
}

export async function doResumeFederationSite(
  siteId: string,
): Promise<FederationActionResponse> {
  const response = await axiosInstance.post<FederationActionResponse>(
    `/api/v1/federation/sites/${encodeURIComponent(siteId)}/resume`,
  );
  return response.data;
}

export async function doRemoveFederationSite(
  siteId: string,
): Promise<FederationActionResponse> {
  const response = await axiosInstance.delete<FederationActionResponse>(
    `/api/v1/federation/sites/${encodeURIComponent(siteId)}`,
  );
  return response.data;
}

export async function doGetFederationSiteSyncStatus(
  siteId: string,
): Promise<FederationSiteSyncStatusResponse> {
  const response =
    await axiosInstance.get<FederationSiteSyncStatusResponse>(
      `/api/v1/federation/sites/${encodeURIComponent(siteId)}/sync-status`,
    );
  return response.data;
}

// ---------------------------------------------------------------------
// Per-site sync-status timeline (Phase 12.2)
// ---------------------------------------------------------------------

/** One point on a site's upstream-sync timeline. */
export interface FederationSyncEvent {
  recorded_at: string | null;
  sync_status: string;
  latency_ms: number | null;
  queue_depth: number | null;
  host_count: number | null;
}

/**
 * Per-site sync-status timeline plus the site's latest self-reported
 * metadata.  ``connection_state`` here is the SITE's own view of its
 * uplink (online / degraded / offline) — when ``offline`` the site is
 * operating in local autonomy mode.  ``capabilities`` is the list of
 * Pro+ engine modules the site advertises.
 */
export interface FederationSiteSyncTimeline {
  licensed: boolean;
  site_id?: string;
  sysmanage_version?: string | null;
  connection_state?: string | null;
  capabilities?: string[];
  last_metadata_at?: string | null;
  events: FederationSyncEvent[];
}

export async function doGetFederationSiteSyncTimeline(
  siteId: string,
  limit = 100,
): Promise<FederationSiteSyncTimeline> {
  const response = await axiosInstance.get<FederationSiteSyncTimeline>(
    `/api/v1/federation/sites/${encodeURIComponent(siteId)}/sync-timeline`,
    { params: { limit } },
  );
  return response.data;
}

// ---------------------------------------------------------------------
// Federation audit log
// ---------------------------------------------------------------------

/**
 * One row from the federation audit log.  Schema mirrors the
 * ``FederationAuditLog`` SQLAlchemy model.  ``target_site_name`` is
 * an engine-side enrichment — when the engine has the site row,
 * it returns the operator-friendly name alongside the raw UUID so
 * the UI doesn't have to join client-side.
 */
export interface FederationAuditEntry {
  id: string;
  created_at: string;
  operation: string;
  actor_userid?: string | null;
  target_site_id?: string | null;
  target_site_name?: string | null;
  target_host_id?: string | null;
  details?: Record<string, unknown> | null;
}

export interface FederationAuditListResponse {
  licensed: boolean;
  entries?: FederationAuditEntry[];
  total?: number;
}

export interface FederationAuditListParams {
  site_id?: string;
  operation?: string;
  actor_userid?: string;
  /** Inclusive lower bound on ``created_at`` (ISO 8601). */
  since?: string;
  /** Exclusive upper bound on ``created_at`` (ISO 8601). */
  until?: string;
  limit?: number;
  offset?: number;
}

/**
 * Fetch federation audit log entries.  Filters compose with AND.
 * The engine is the source of truth for ordering (newest first by
 * convention); the OSS stub returns ``[]`` regardless.
 */
export async function doListFederationAuditLog(
  params: FederationAuditListParams = {},
): Promise<FederationAuditListResponse> {
  const response = await axiosInstance.get<FederationAuditListResponse>(
    "/api/v1/federation/audit",
    { params },
  );
  return response.data;
}

// ---------------------------------------------------------------------
// Site-side stub: enrollment status (the site-engine surface — same
// envelope shape).  Used by the Sites map's per-site connectivity
// badge when running on a coordinator.  Kept here next to the rest
// of the federation surface so route names live in one place.
// ---------------------------------------------------------------------

export interface FederationSiteEnrollmentStatusResponse {
  licensed: boolean;
  status?: string;
}

// ---------------------------------------------------------------------
// Module-scoped license probe (Phase 12.3 UI gating)
//
// The OSS rule is "don't show menus for features that aren't available".
// Every federation page already renders an Enterprise upsell on
// ``licensed: false`` — but the navbar entry and in-page action
// buttons would otherwise be reachable when the engine isn't loaded.
// To hide them, we probe ``/api/v1/federation/sites`` once per page
// load and cache the result in module scope so subsequent calls
// (from Navbar, Sites header, etc.) don't re-fetch.
// ---------------------------------------------------------------------

let _federationLicensedCache: boolean | null = null;
let _federationLicensedPromise: Promise<boolean> | null = null;

/**
 * Resolve the cached licensed flag (or fetch it if we haven't yet).
 * Always resolves — any network / engine error is treated as
 * "not licensed" so the menu hides rather than flashes.
 *
 * Skipped entirely when there's no bearer token: the Navbar lives
 * outside ``<Routes>`` in ``App.tsx`` and therefore mounts on the
 * ``/login`` page too.  If we fire the probe pre-auth, the API call
 * 401s, axios's response interceptor tries ``/refresh``, that also
 * 401s, and ``handle401Refresh`` does ``location.href = '/login'``,
 * triggering a full page reload — which remounts Navbar, fires the
 * probe again, and loops indefinitely.  The short-circuit caches a
 * ``false`` result so the loop never starts; ``_resetFederationLicensedCacheForTests``
 * clears it after login so the next mount re-fires the real probe.
 */
export function probeFederationLicensed(): Promise<boolean> {
  if (_federationLicensedCache !== null) {
    return Promise.resolve(_federationLicensedCache);
  }
  if (_federationLicensedPromise !== null) {
    return _federationLicensedPromise;
  }
  if (typeof localStorage !== 'undefined' && !localStorage.getItem('bearer_token')) {
    return Promise.resolve(false);
  }
  _federationLicensedPromise = doListFederationSites()
    .then((data) => {
      _federationLicensedCache = Boolean(data.licensed);
      return _federationLicensedCache;
    })
    .catch(() => {
      _federationLicensedCache = false;
      return false;
    });
  return _federationLicensedPromise;
}

/**
 * React hook for gating UI on the federation-engine licensed flag.
 * Returns ``loading=true`` for the first render after mount so
 * components can choose whether to flash the menu or just leave a
 * gap — Navbar uses the latter (renders nothing until resolved).
 */
export function useFederationLicensed(): {
  loading: boolean;
  licensed: boolean;
} {
  const [state, setState] = useState<{ loading: boolean; licensed: boolean }>(
    () => ({
      // If the probe already resolved earlier in this page load,
      // skip the loading flash entirely.
      loading: _federationLicensedCache === null,
      licensed: _federationLicensedCache === true,
    }),
  );
  useEffect(() => {
    let cancelled = false;
    probeFederationLicensed().then((licensed) => {
      if (!cancelled) {
        setState({ loading: false, licensed });
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return state;
}

/**
 * Test-only: clear the module-scope cache.  Production code never
 * calls this; the cache is the right behaviour at runtime since the
 * engine load state is fixed for the life of the page.
 */
export function _resetFederationLicensedCacheForTests(): void {
  _federationLicensedCache = null;
  _federationLicensedPromise = null;
}

// ---------------------------------------------------------------------
// Federation policies (Phase 12.1.F + 12.3 policy UI)
// ---------------------------------------------------------------------

/**
 * Coordinator-defined policy that gets pushed to sites.  Polymorphic
 * by ``policy_type`` (update_profile, firewall_role, compliance_baseline,
 * ...); the type-specific body is in ``definition_json`` as a JSON
 * string the UI shows as a code-editor.
 */
export interface FederationPolicy {
  id: string;
  policy_type: string;
  name: string;
  description?: string | null;
  definition_json: string;
  version: number;
  is_active: boolean;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface FederationPolicyAssignment {
  policy_id: string;
  site_id: string;
  /** Coordinator-side name of the assigned site — engine-enriched
   * so the UI doesn't have to join client-side. */
  site_name?: string | null;
  assigned_at?: string | null;
  assigned_by?: string | null;
  /**
   * Lifecycle of the per-(policy, site) push:
   *
   *   pending       — never pushed (or operator re-assigned to reset).
   *   pushed        — at least one successful delivery.
   *   acknowledged  — site applied the policy (reserved for future).
   *   error         — most recent attempt failed; backoff window active.
   *   dead          — Phase 12.10 hardening: exceeded MAX_ATTEMPTS,
   *                   no further retries until operator re-assigns.
   */
  push_status: string;
  last_push_attempt_at?: string | null;
  last_push_error?: string | null;
  pushed_version?: number | null;
  /** Phase 12.10 hardening: total transport attempts (success + fail).
   *  Reset to 0 on re-assignment.  When >= 8 the row dead-letters. */
  push_attempts?: number;
}

export interface FederationPolicyListResponse {
  licensed: boolean;
  policies?: FederationPolicy[];
}

export interface FederationPolicyDetailResponse {
  licensed: boolean;
  policy?: FederationPolicy;
  assignments?: FederationPolicyAssignment[];
}

export interface FederationPolicyActionResponse {
  licensed: boolean;
  policy?: FederationPolicy;
  assignments?: FederationPolicyAssignment[];
}

export interface FederationPolicyCreateRequest {
  policy_type: string;
  name: string;
  description?: string | null;
  /** Native dict; serialised server-side. */
  definition: Record<string, unknown>;
}

export interface FederationPolicyUpdateRequest {
  name?: string;
  description?: string | null;
  definition?: Record<string, unknown>;
}

export async function doListFederationPolicies(
  params: { policy_type?: string; active_only?: boolean } = {},
): Promise<FederationPolicyListResponse> {
  const response = await axiosInstance.get<FederationPolicyListResponse>(
    "/api/v1/federation/policies",
    { params },
  );
  return response.data;
}

export async function doGetFederationPolicy(
  policyId: string,
): Promise<FederationPolicyDetailResponse> {
  const response = await axiosInstance.get<FederationPolicyDetailResponse>(
    `/api/v1/federation/policies/${encodeURIComponent(policyId)}`,
  );
  return response.data;
}

export async function doCreateFederationPolicy(
  body: FederationPolicyCreateRequest,
): Promise<FederationPolicyActionResponse> {
  const response = await axiosInstance.post<FederationPolicyActionResponse>(
    "/api/v1/federation/policies",
    body,
  );
  return response.data;
}

export async function doUpdateFederationPolicy(
  policyId: string,
  body: FederationPolicyUpdateRequest,
): Promise<FederationPolicyActionResponse> {
  const response = await axiosInstance.patch<FederationPolicyActionResponse>(
    `/api/v1/federation/policies/${encodeURIComponent(policyId)}`,
    body,
  );
  return response.data;
}

export async function doDeactivateFederationPolicy(
  policyId: string,
): Promise<FederationPolicyActionResponse> {
  const response =
    await axiosInstance.delete<FederationPolicyActionResponse>(
      `/api/v1/federation/policies/${encodeURIComponent(policyId)}`,
    );
  return response.data;
}

export async function doAssignFederationPolicy(
  policyId: string,
  siteIds: string[],
): Promise<FederationPolicyActionResponse> {
  const response = await axiosInstance.post<FederationPolicyActionResponse>(
    `/api/v1/federation/policies/${encodeURIComponent(policyId)}/assign`,
    { site_ids: siteIds },
  );
  return response.data;
}

export async function doPushFederationPolicy(
  policyId: string,
): Promise<FederationPolicyActionResponse> {
  const response = await axiosInstance.post<FederationPolicyActionResponse>(
    `/api/v1/federation/policies/${encodeURIComponent(policyId)}/push`,
  );
  return response.data;
}

/** Per-site "Push policies now": requeues every policy assigned to the
 * site for re-delivery on the next push-worker tick. */
export interface FederationRepushResponse {
  licensed: boolean;
  requeued_count?: number;
}

export async function doRepushSitePolicies(
  siteId: string,
): Promise<FederationRepushResponse> {
  const response = await axiosInstance.post<FederationRepushResponse>(
    `/api/v1/federation/sites/${encodeURIComponent(siteId)}/repush-policies`,
  );
  return response.data;
}

// ---------------------------------------------------------------------
// Alert thresholds (Phase 12.1 — operator-configurable)
// ---------------------------------------------------------------------

/** The four configurable rollup-alert thresholds.  A null override means
 * "use the built-in default" (reflected in ``effective``). */
export interface FederationAlertThresholds {
  offline_multiplier: number | null;
  min_offline_seconds: number | null;
  compliance_threshold: number | null;
  critical_cve_threshold: number | null;
}

export interface FederationAlertConfigResponse {
  licensed: boolean;
  effective?: FederationAlertThresholds;
  overrides?: FederationAlertThresholds;
}

export async function doGetFederationAlertConfig(): Promise<FederationAlertConfigResponse> {
  const response = await axiosInstance.get<FederationAlertConfigResponse>(
    `/api/v1/federation/alert-config`,
  );
  return response.data;
}

export async function doUpdateFederationAlertConfig(
  overrides: Partial<FederationAlertThresholds>,
): Promise<FederationAlertConfigResponse> {
  const response = await axiosInstance.put<FederationAlertConfigResponse>(
    `/api/v1/federation/alert-config`,
    overrides,
  );
  return response.data;
}

// ---------------------------------------------------------------------
// Dispatched commands (coordinator → site)
// ---------------------------------------------------------------------

export interface FederationDispatchedCommand {
  id: string;
  command_type: string;
  parameters?: Record<string, unknown> | null;
  target_site_id: string;
  target_host_ids?: string[];
  dispatched_by?: string | null;
  dispatched_at?: string | null;
  /** queued_at_site / in_progress / partial / completed / failed */
  status: string;
  result_summary?: string | null;
  completed_at?: string | null;
  /** Phase 12.10 hardening: transport-attempt counter.  When >=
   *  MAX_ATTEMPTS the coordinator dead-letters the command (status
   *  forced to ``failed``); operator must redispatch. */
  push_attempts?: number;
  last_push_attempt_at?: string | null;
  last_push_error?: string | null;
}

export interface FederationCommandListResponse {
  licensed: boolean;
  commands?: FederationDispatchedCommand[];
}

/**
 * List dispatched commands targeting a specific site.  The operator
 * UI uses this to render a "what's queued / in flight / failed" panel
 * on the SiteDetail page.  ``open_only=true`` excludes terminal
 * statuses (completed / failed / partial).
 */
export async function doListFederationCommands(params: {
  site_id?: string;
  status?: string;
  open_only?: boolean;
  limit?: number;
  offset?: number;
}): Promise<FederationCommandListResponse> {
  const search = new URLSearchParams();
  if (params.site_id) search.set("site_id", params.site_id);
  if (params.status) search.set("status", params.status);
  if (params.open_only) search.set("open_only", "true");
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const qs = search.toString();
  const query = qs ? `?${qs}` : "";
  const response = await axiosInstance.get<FederationCommandListResponse>(
    `/api/v1/federation/commands${query}`,
  );
  return response.data;
}

// ---------------------------------------------------------------------
// Per-site rollups (Phase 12.3 — cross-site compliance/vuln drill-down)
// ---------------------------------------------------------------------

export interface FederationComplianceRollup {
  baseline: string;
  score_percent: number;
  hosts_in_scope: number;
  hosts_compliant: number;
  hosts_noncompliant: number;
  snapshot_at?: string | null;
}

export interface FederationVulnerabilityRollup {
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  affected_host_count: number;
  top_cve_ids?: string[];
  snapshot_at?: string | null;
}

export interface FederationDashboardRollupResponse {
  licensed: boolean;
  host_rollup?: {
    host_count: number;
    active_count: number;
    snapshot_at?: string | null;
  } | null;
  compliance_rollups?: FederationComplianceRollup[];
  vulnerability_rollup?: FederationVulnerabilityRollup | null;
}

/**
 * Latest synced compliance + vulnerability rollup for one site.  This is
 * the federation-correct "cross-site compliance/vuln drill-down": the
 * coordinator serves the per-site AGGREGATE snapshots the site pushed up
 * (not per-host detail — that lives on the site).  Returns
 * ``{licensed:false}`` on OSS.
 */
export async function doGetFederationDashboardRollup(
  siteId: string,
): Promise<FederationDashboardRollupResponse> {
  const response = await axiosInstance.get<FederationDashboardRollupResponse>(
    `/api/v1/federation/rollups/dashboard?site_id=${encodeURIComponent(siteId)}`,
  );
  return response.data;
}

// ---------------------------------------------------------------------
// Rollup alerts (Phase 12.1 — cross-site alerting)
// ---------------------------------------------------------------------

export interface FederationAlert {
  id: string;
  site_id: string;
  /** site_offline | compliance_below | vulnerabilities_high */
  condition: string;
  /** warning | critical */
  severity: string;
  title: string;
  message: string;
  details?: Record<string, unknown> | null;
  triggered_at?: string | null;
  resolved: boolean;
  resolved_at?: string | null;
  acknowledged: boolean;
  acknowledged_at?: string | null;
}

export interface FederationAlertListResponse {
  licensed: boolean;
  alerts?: FederationAlert[];
}

export interface FederationAlertAckResponse {
  licensed: boolean;
  alert?: FederationAlert | null;
}

/** List federation rollup alerts (open-only by default). */
export async function doListFederationAlerts(params: {
  site_id?: string;
  include_resolved?: boolean;
  limit?: number;
}): Promise<FederationAlertListResponse> {
  const search = new URLSearchParams();
  if (params.site_id) search.set("site_id", params.site_id);
  if (params.include_resolved) search.set("include_resolved", "true");
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const qs = search.toString();
  const query = qs ? `?${qs}` : "";
  const response = await axiosInstance.get<FederationAlertListResponse>(
    `/api/v1/federation/alerts${query}`,
  );
  return response.data;
}

/** Acknowledge an open alert. */
export async function doAcknowledgeFederationAlert(
  alertId: string,
): Promise<FederationAlertAckResponse> {
  const response = await axiosInstance.post<FederationAlertAckResponse>(
    `/api/v1/federation/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    {},
  );
  return response.data;
}

export interface FederationDispatchCommandRequest {
  command_type: string;
  target_site_id: string;
  /** Command-type-specific payload (e.g. {package_names:[…]}, {script:"…"}). */
  parameters?: Record<string, unknown> | null;
  /** Specific hosts at the site; omit/empty ⇒ all hosts at the site. */
  target_host_ids?: string[] | null;
}

export interface FederationDispatchCommandResponse {
  licensed: boolean;
  command?: FederationDispatchedCommand;
}

/**
 * Dispatch a command to a subordinate site (and optionally specific hosts
 * at that site).  The coordinator queues it; the site's actuation worker
 * fans it out to local agents and reports results back upstream — nothing
 * is executed synchronously here.  Returns the created command record so
 * the caller can show it immediately.
 */
export async function doDispatchFederationCommand(
  body: FederationDispatchCommandRequest,
): Promise<FederationDispatchCommandResponse> {
  const response = await axiosInstance.post<FederationDispatchCommandResponse>(
    `/api/v1/federation/commands/dispatch`,
    body,
  );
  return response.data;
}

// ---------------------------------------------------------------------
// Cross-site host directory (Phase 12.3 — federated Hosts page)
// ---------------------------------------------------------------------

/**
 * One row of the coordinator's synced cross-site host directory.  This
 * is the SUMMARY tier — the coordinator never holds full per-host
 * detail; the ``site_detail_url`` on the detail endpoint deep-links to
 * the owning site's own UI for that.  Mirrors the engine's
 * ``_host_directory_to_dict``.
 */
export interface FederationHostDirectoryEntry {
  host_id: string;
  site_id: string;
  fqdn?: string | null;
  ipv4?: string | null;
  ipv6?: string | null;
  public_ip?: string | null;
  os_family?: string | null;
  os_version?: string | null;
  platform?: string | null;
  status?: string | null;
  last_seen?: string | null;
  tags_json?: string | null;
  geo_country_code?: string | null;
  geo_subdivision_code?: string | null;
  geo_city?: string | null;
  geo_latitude?: number | null;
  geo_longitude?: number | null;
  mtime?: string | null;
}

export interface FederationHostSearchResponse {
  licensed: boolean;
  hosts?: FederationHostDirectoryEntry[];
  /** Total matches across all pages, for "showing X of N" + paging. */
  total?: number;
}

/**
 * Owning-site descriptor returned alongside a host's detail so the UI
 * can render "lives at <name>" and a click-through.
 */
export interface FederationHostSite {
  site_id: string;
  name: string;
  url: string;
}

export interface FederationHostDetailResponse {
  licensed: boolean;
  host?: FederationHostDirectoryEntry | null;
  /** Owning site, or null if it was removed after the row synced. */
  site?: FederationHostSite | null;
  /**
   * Deep-link into the OWNING SITE's own web UI for this host's live
   * detail.  Drill-down is navigational, not a synchronous proxy — the
   * coordinator never blocks on a subordinate to answer a read.
   */
  site_detail_url?: string | null;
}

/**
 * Paginated cross-site host search.  ``site_id`` narrows to one site
 * (drives the "See hosts at this site" link from SiteDetail); the other
 * filters compose with AND, and ``free_text`` ORs across fqdn / ipv4 /
 * public_ip for the search box.  Returns ``{licensed:false}`` on OSS.
 */
export async function doSearchFederationHosts(params: {
  site_id?: string;
  fqdn_contains?: string;
  ipv4_contains?: string;
  os_family?: string;
  platform?: string;
  status?: string;
  geo_country_code?: string;
  free_text?: string;
  order_by?: string;
  limit?: number;
  offset?: number;
}): Promise<FederationHostSearchResponse> {
  const search = new URLSearchParams();
  const set = (k: string, v: string | number | undefined) => {
    if (v !== undefined && v !== "") search.set(k, String(v));
  };
  set("site_id", params.site_id);
  set("fqdn_contains", params.fqdn_contains);
  set("ipv4_contains", params.ipv4_contains);
  set("os_family", params.os_family);
  set("platform", params.platform);
  set("status", params.status);
  set("geo_country_code", params.geo_country_code);
  set("free_text", params.free_text);
  set("order_by", params.order_by);
  set("limit", params.limit);
  set("offset", params.offset);
  const qs = search.toString();
  const query = qs ? `?${qs}` : "";
  const response = await axiosInstance.get<FederationHostSearchResponse>(
    `/api/v1/federation/hosts${query}`,
  );
  return response.data;
}

/**
 * Fetch a single directory entry plus its owning site + the deep-link
 * to that site's live host detail.
 */
export async function doGetFederationHostDetail(
  hostId: string,
): Promise<FederationHostDetailResponse> {
  const response = await axiosInstance.get<FederationHostDetailResponse>(
    `/api/v1/federation/hosts/${encodeURIComponent(hostId)}`,
  );
  return response.data;
}

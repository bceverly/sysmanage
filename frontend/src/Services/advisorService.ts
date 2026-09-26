// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from "./api";

/**
 * The advisor (Phase 21.2): rules over host evidence, per-host outcomes, risk
 * scores, remediation proposals and curated packs. Enterprise -- every call
 * here fails on a server without `advisor_engine`.
 *
 * FOUR OUTCOMES, AND ONE OF THEM IS NOT A FINDING AND NOT CLEAN
 * `not_assessable` means the advisor could not evaluate the rule on that host
 * (evidence missing, stale or uncollected). The UI must show it, with its
 * reason, beside the findings -- never fold it into "no recommendations".
 */

export type AdvisorOutcome = "fires" | "does_not_fire" | "not_assessable" | "not_applicable";
export type AdvisorLevel = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "NONE" | "UNKNOWN";
export type AdvisorProposalStatus = "proposed" | "approved" | "rejected" | "withdrawn" | "failed";

export interface AdvisorGap {
  evidence: string;
  reason: string;
  columns?: string[];
  age_days?: number;
  max_age_days?: number;
  detail?: string;
  peers?: number;
}

export interface AdvisorRule {
  source: "shared" | "tenant";
  key: string;
  title: string | null;
  lens: string | null;
  scope: string;
  impact: number | null;
  likelihood: number | null;
  id?: string;
  pack?: string | null;
  enabled?: boolean;
  errors: { code: string; field: string; detail?: unknown }[];
}

export interface AdvisorHostScore {
  score: number | null;
  level: AdvisorLevel;
  complete: boolean;
  counts: Record<AdvisorOutcome, number>;
  worst_risk: number | null;
  evaluated_at?: string | null;
}

export interface AdvisorFleetScore {
  total_hosts: number;
  assessed_hosts: number;
  unknown_hosts: number;
  incomplete_hosts: number;
  average_score: number | null;
  max_score: number | null;
  level: AdvisorLevel;
  hosts_by_level: Record<AdvisorLevel, number>;
}

export interface AdvisorFeedEntry {
  source: "shared" | "tenant";
  key: string;
  rule: AdvisorRule | null;
  risk: number | null;
  hosts_firing: number;
  hosts_not_assessable: number;
  hosts_not_applicable: number;
  hosts_clean: number;
  gap_reasons: Record<string, number>;
}

export interface AdvisorFeed {
  fleet: AdvisorFleetScore;
  totals: { findings: number; not_assessable: number; not_applicable: number; clean: number };
  rules: AdvisorFeedEntry[];
}

export interface AdvisorResult {
  source: "shared" | "tenant";
  key: string;
  title: string | null;
  lens: string | null;
  outcome: AdvisorOutcome;
  impact: number | null;
  likelihood: number | null;
  risk: number | null;
  evaluated_at: string | null;
  match_count?: number;
  matches?: Record<string, unknown>[];
  remediation?: string[];
  gaps?: AdvisorGap[];
  proposal?: { id: string; status: AdvisorProposalStatus; kind: string } | null;
  host_id?: string;
  fqdn?: string;
}

export interface AdvisorHostView {
  host_id: string;
  fqdn: string;
  score: AdvisorHostScore;
  findings: AdvisorResult[];
  not_assessable: AdvisorResult[];
  not_applicable: AdvisorResult[];
  clean: AdvisorResult[];
}

export interface AdvisorProposal {
  id: string;
  host_id: string;
  fqdn: string | null;
  source: string;
  key: string;
  kind: "profile" | "generate";
  profile_name: string | null;
  engine: string | null;
  content: string | null;
  packages: string[];
  skipped: number;
  status: AdvisorProposalStatus;
  reason: string | null;
  created_at: string | null;
  decided_by: string | null;
  decided_at: string | null;
  command_id: string | null;
  run: { success: boolean; completed_at: string | null } | null;
}

export interface AdvisorPack {
  slug: string;
  name: string;
  description: string | null;
  version: number;
  deprecated: boolean;
  default_enabled: boolean;
  choice: boolean | null;
  enabled: boolean;
  disabled_rules: string[];
  rules: { key: string; title: string | null; lens: string | null; scope: string; enabled: boolean }[];
}

export const advisorService = {
  async getFeed(lens?: string): Promise<AdvisorFeed> {
    const response = await axiosInstance.get("/api/v1/advisor/feed", {
      params: lens ? { lens } : undefined,
    });
    return response.data;
  },

  async getHost(hostId: string): Promise<AdvisorHostView> {
    const response = await axiosInstance.get(`/api/v1/advisor/hosts/${hostId}`);
    return response.data;
  },

  async getRuleHosts(
    source: string,
    key: string,
    outcome?: AdvisorOutcome,
  ): Promise<{ rule: AdvisorRule | null; hosts: AdvisorResult[] }> {
    const response = await axiosInstance.get(
      `/api/v1/advisor/rules/${encodeURIComponent(source)}/${encodeURIComponent(key)}/hosts`,
      { params: outcome ? { outcome } : undefined },
    );
    return response.data;
  },

  async listProposals(status?: AdvisorProposalStatus, hostId?: string): Promise<AdvisorProposal[]> {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    if (hostId) params.host_id = hostId;
    const response = await axiosInstance.get("/api/v1/advisor/proposals", { params });
    return response.data.proposals;
  },

  async approveProposal(id: string): Promise<AdvisorProposal> {
    const response = await axiosInstance.post(`/api/v1/advisor/proposals/${id}/approve`);
    return response.data;
  },

  async rejectProposal(id: string): Promise<AdvisorProposal> {
    const response = await axiosInstance.post(`/api/v1/advisor/proposals/${id}/reject`);
    return response.data;
  },

  async listPacks(): Promise<AdvisorPack[]> {
    const response = await axiosInstance.get("/api/v1/advisor/packs");
    return response.data.packs;
  },

  async choosePack(
    slug: string,
    choice: { enabled?: boolean | null; disabled_rules?: string[] },
  ): Promise<AdvisorPack> {
    const response = await axiosInstance.put(
      `/api/v1/advisor/packs/${encodeURIComponent(slug)}`,
      choice,
    );
    return response.data;
  },

  async evaluate(): Promise<Record<string, number>> {
    const response = await axiosInstance.post("/api/v1/advisor/evaluate");
    return response.data;
  },
};

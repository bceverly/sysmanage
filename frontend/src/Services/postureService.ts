// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from "./api";

/**
 * The threat model and the posture punch list (Phase 21.4). Enterprise --
 * every call fails on a server without `advisor_engine`.
 *
 * FOUR STATES, AND WAIVED IS NOT GREEN
 * `satisfied`, `open`, `not_assessable` come from the evaluation; `waived` is
 * an overlay on an OPEN item (an audited acceptance of risk). The item still
 * evaluates open underneath (`evaluated_state`), and a waived item is never
 * shown as a pass.
 */

export type PostureState = "satisfied" | "open" | "waived" | "not_assessable";
export type RemedyKind = "setting" | "fleet" | "guided" | "none" | null;

export interface QuestionOption {
  id: string;
  sets?: string[];
}

export interface Question {
  id: string;
  kind: "one" | "many";
  options: QuestionOption[];
  show_if?: Record<string, Record<string, string[]>>;
  required?: boolean;
}

export interface Questionnaire {
  id: string;
  version: number;
  attributes: Record<string, string>;
  questions: Question[];
}

export type Answers = Record<string, string | string[]>;

export interface ThreatModel {
  id: string;
  model_version: number;
  questionnaire: string;
  questionnaire_version: number;
  attributes: Record<string, boolean>;
  answers: Answers;
  digest: string;
  complete: boolean;
  missing: string[];
  ignored: string[];
  created_by: string | null;
  created_at: string | null;
}

export interface ThreatModelVersion {
  model_version: number;
  created_by: string | null;
  created_at: string | null;
  complete: boolean;
}

export interface ModelChanges {
  attributes_on: string[];
  attributes_off: string[];
  answers_changed: string[];
}

export interface Waiver {
  id: string;
  reason: string;
  granted_by: string;
  granted_at: string | null;
  reaffirmed_by: string | null;
  reaffirmed_at: string | null;
  stale_reason: string | null;
  stale_since: string | null;
  risk: number | null;
  rule_version: number | null;
  basis_attributes: Record<string, boolean>;
}

export interface Coverage {
  hosts_total: number;
  hosts_ok: number;
  hosts_failing: number;
  hosts_unknown: number;
}

export interface PostureItem {
  rule_key: string;
  rule_source: string;
  rule_version: number | null;
  state: PostureState;
  evaluated_state: PostureState;
  waiver: Waiver | null;
  remedy: string | null;
  remedy_kind: RemedyKind;
  remedy_target: string | null;
  outcome: string;
  managed_by: "server" | "tenant";
  impact: number | null;
  likelihood: number | null;
  risk: number | null;
  gaps: { evidence: string; reason: string; hosts_unknown?: number; hosts_total?: number }[];
  coverage: Coverage | null;
  evaluated_at: string | null;
  state_changed_at: string | null;
  evaluated_under_current_model: boolean;
  regressed: boolean;
}

export interface PostureList {
  threat_model: ThreatModel | null;
  totals: Partial<Record<PostureState, number>>;
  items: PostureItem[];
}

export interface RemedyPreview {
  remedy: string | null;
  kind: RemedyKind;
  available: boolean;
  unavailable_reason: string | null;
  target: string | null;
  changes: { setting: string; from: unknown; to: unknown }[];
  hosts: { id: string; fqdn: string }[];
}

export interface RemedyResult {
  applied: boolean;
  changes: RemedyPreview["changes"];
  hosts: RemedyPreview["hosts"];
  failed: { fqdn: string; reason: string }[];
}

export interface PostureEvent {
  rule_key: string;
  kind: string;
  from_state: string | null;
  to_state: string | null;
  cause: string;
  threat_model_version: number | null;
  at: string | null;
}

export interface ModelDiff {
  from_version: number;
  to_version: number;
  model: ModelChanges;
  punch_list: PostureEvent[];
}

const base = "/api/v1/advisor";
const item = (key: string) => `${base}/posture/${encodeURIComponent(key)}`;

export const postureService = {
  async getQuestionnaire(): Promise<Questionnaire> {
    return (await axiosInstance.get(`${base}/threat-model/questionnaire`)).data;
  },

  async getThreatModel(): Promise<{ current: ThreatModel | null; versions: ThreatModelVersion[] }> {
    return (await axiosInstance.get(`${base}/threat-model`)).data;
  },

  async saveThreatModel(answers: Answers): Promise<{ threat_model: ThreatModel; changes: ModelChanges }> {
    return (await axiosInstance.post(`${base}/threat-model`, { answers })).data;
  },

  async getDiff(fromVersion: number, toVersion: number): Promise<ModelDiff> {
    return (await axiosInstance.get(`${base}/threat-model/diff`, {
      params: { from_version: fromVersion, to_version: toVersion },
    })).data;
  },

  async getPosture(): Promise<PostureList> {
    return (await axiosInstance.get(`${base}/posture`)).data;
  },

  async getHistory(ruleKey?: string, limit = 200): Promise<PostureEvent[]> {
    const url = ruleKey ? `${item(ruleKey)}/history` : `${base}/posture/history`;
    return (await axiosInstance.get(url, { params: { limit } })).data.events;
  },

  async waive(ruleKey: string, reason: string): Promise<Waiver> {
    return (await axiosInstance.post(`${item(ruleKey)}/waiver`, { reason })).data.waiver;
  },

  async revokeWaiver(ruleKey: string): Promise<Waiver> {
    return (await axiosInstance.delete(`${item(ruleKey)}/waiver`)).data.waiver;
  },

  async reaffirmWaiver(ruleKey: string, reason?: string): Promise<Waiver> {
    const body = reason ? { reason } : undefined;
    return (await axiosInstance.post(`${item(ruleKey)}/waiver/reaffirm`, body)).data.waiver;
  },

  async previewRemedy(ruleKey: string): Promise<RemedyPreview> {
    return (await axiosInstance.get(`${item(ruleKey)}/remedy`)).data;
  },

  async applyRemedy(ruleKey: string): Promise<RemedyResult> {
    return (await axiosInstance.post(`${item(ruleKey)}/remedy`)).data;
  },
};

/** The server's refusal code (409 `{detail: {code}}`), or null. */
export const refusalCode = (err: unknown): string | null => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return detail && typeof detail === "object" && "code" in detail
    ? String(detail.code)
    : null;
};

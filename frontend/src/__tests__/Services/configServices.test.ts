// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, test, expect } from "vitest";

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import axiosInstance from "../../Services/api";
import * as fleet from "../../Services/configFleetService";
import * as cm from "../../Services/configManagementService";
import * as qp from "../../Services/queryPackService";

type Method = "get" | "post" | "put" | "delete";

const mocks: Record<Method, ReturnType<typeof vi.fn>> = {
  get: axiosInstance.get as unknown as ReturnType<typeof vi.fn>,
  post: axiosInstance.post as unknown as ReturnType<typeof vi.fn>,
  put: axiosInstance.put as unknown as ReturnType<typeof vi.fn>,
  delete: axiosInstance.delete as unknown as ReturnType<typeof vi.fn>,
};

const DATA = { sentinel: "payload" };

interface Case {
  name: string;
  call: () => Promise<unknown>;
  method: Method;
  args: unknown[];
  returnsData?: boolean;
}

const FB = "/api/v1/config-management";
const QB = "/api/v1/query-packs";

const fleetCases: Case[] = [
  { name: "getInventories", call: () => fleet.getInventories(), method: "get", args: [`${FB}/inventories`] },
  { name: "createInventory", call: () => fleet.createInventory({ name: "web" }), method: "post", args: [`${FB}/inventories`, { name: "web" }] },
  { name: "updateInventory", call: () => fleet.updateInventory("i1", { all_hosts: true }), method: "put", args: [`${FB}/inventories/i1`, { all_hosts: true }] },
  { name: "deleteInventory", call: () => fleet.deleteInventory("i1"), method: "delete", args: [`${FB}/inventories/i1`], returnsData: false },
  { name: "getInventoryMembers", call: () => fleet.getInventoryMembers("i1"), method: "get", args: [`${FB}/inventories/i1/members`] },
  { name: "addInventoryMember", call: () => fleet.addInventoryMember("i1", { host_id: "h1" }), method: "post", args: [`${FB}/inventories/i1/members`, { host_id: "h1" }] },
  { name: "deleteInventoryMember", call: () => fleet.deleteInventoryMember("m1"), method: "delete", args: [`${FB}/inventory-members/m1`], returnsData: false },
  { name: "previewInventory", call: () => fleet.previewInventory("i1"), method: "get", args: [`${FB}/inventories/i1/hosts`] },
  { name: "getJobTemplates", call: () => fleet.getJobTemplates(), method: "get", args: [`${FB}/job-templates`] },
  {
    name: "createJobTemplate",
    call: () => fleet.createJobTemplate({ name: "t" } as fleet.ConfigJobTemplateRequest),
    method: "post",
    args: [`${FB}/job-templates`, { name: "t" }],
  },
  { name: "updateJobTemplate", call: () => fleet.updateJobTemplate("t1", { name: "n" }), method: "put", args: [`${FB}/job-templates/t1`, { name: "n" }] },
  { name: "deleteJobTemplate", call: () => fleet.deleteJobTemplate("t1"), method: "delete", args: [`${FB}/job-templates/t1`], returnsData: false },
  { name: "launchJobTemplate", call: () => fleet.launchJobTemplate("t1"), method: "post", args: [`${FB}/job-templates/t1/launch`, {}] },
  { name: "getJobs default limit", call: () => fleet.getJobs(), method: "get", args: [`${FB}/jobs`, { params: { limit: 25 } }] },
  { name: "getJobs explicit limit", call: () => fleet.getJobs(5), method: "get", args: [`${FB}/jobs`, { params: { limit: 5 } }] },
  { name: "getJob", call: () => fleet.getJob("j1"), method: "get", args: [`${FB}/jobs/j1`] },
  { name: "getJobTargets default", call: () => fleet.getJobTargets("j1"), method: "get", args: [`${FB}/jobs/j1/targets`, { params: { limit: 100 } }] },
  { name: "getJobTargets limit", call: () => fleet.getJobTargets("j1", 7), method: "get", args: [`${FB}/jobs/j1/targets`, { params: { limit: 7 } }] },
  { name: "cancelJob no reason", call: () => fleet.cancelJob("j1"), method: "post", args: [`${FB}/jobs/j1/cancel`, { reason: null }] },
  { name: "cancelJob reason", call: () => fleet.cancelJob("j1", "oops"), method: "post", args: [`${FB}/jobs/j1/cancel`, { reason: "oops" }] },
  { name: "getRemediationRules", call: () => fleet.getRemediationRules(), method: "get", args: [`${FB}/remediation-rules`] },
  {
    name: "createRemediationRule",
    call: () => fleet.createRemediationRule({ name: "r" } as fleet.ConfigRemediationRuleRequest),
    method: "post",
    args: [`${FB}/remediation-rules`, { name: "r" }],
  },
  { name: "updateRemediationRule", call: () => fleet.updateRemediationRule("r1", { name: "x" }), method: "put", args: [`${FB}/remediation-rules/r1`, { name: "x" }] },
  { name: "deleteRemediationRule", call: () => fleet.deleteRemediationRule("r1"), method: "delete", args: [`${FB}/remediation-rules/r1`], returnsData: false },
  { name: "getFindingRemediation", call: () => fleet.getFindingRemediation("f1"), method: "get", args: [`${FB}/drift/findings/f1/remediation`] },
  { name: "repairFinding", call: () => fleet.repairFinding("f1"), method: "post", args: [`${FB}/drift/findings/f1/remediate`, {}] },
];

const cmCases: Case[] = [
  { name: "getConfigMgmtPrereq", call: () => cm.getConfigMgmtPrereq("h1"), method: "get", args: ["/api/v1/hosts/h1/config-management/prerequisite"] },
  { name: "installConfigMgmtPrereq default", call: () => cm.installConfigMgmtPrereq("h1"), method: "post", args: ["/api/v1/hosts/h1/config-management/prerequisite/install"] },
  {
    name: "installConfigMgmtPrereq engine",
    call: () => cm.installConfigMgmtPrereq("h1", "salt minion"),
    method: "post",
    args: ["/api/v1/hosts/h1/config-management/prerequisite/install?engine=salt%20minion"],
  },
  { name: "getConfigProfileRuns default", call: () => cm.getConfigProfileRuns("h1"), method: "get", args: ["/api/v1/hosts/h1/config-management/runs?limit=25"] },
  { name: "getConfigProfileRuns limit", call: () => cm.getConfigProfileRuns("h1", 3), method: "get", args: ["/api/v1/hosts/h1/config-management/runs?limit=3"] },
  { name: "getConfigProfileRun", call: () => cm.getConfigProfileRun("r1"), method: "get", args: ["/api/v1/config-management/runs/r1"] },
  {
    name: "applyConfigProfile",
    call: () => cm.applyConfigProfile("h1", { profile_id: "p1" } as cm.ConfigProfileApplyRequest),
    method: "post",
    args: ["/api/v1/hosts/h1/config-management/apply", { profile_id: "p1" }],
  },
  { name: "getConfigMgmtEngines", call: () => cm.getConfigMgmtEngines("h1"), method: "get", args: ["/api/v1/hosts/h1/config-management/engines"] },
  { name: "getConfigProfiles all", call: () => cm.getConfigProfiles(), method: "get", args: ["/api/v1/config-management/profiles"] },
  { name: "getConfigProfiles engine", call: () => cm.getConfigProfiles("ansible"), method: "get", args: ["/api/v1/config-management/profiles?engine=ansible"] },
  { name: "getConfigProfile", call: () => cm.getConfigProfile("p1"), method: "get", args: ["/api/v1/config-management/profiles/p1"] },
  {
    name: "createConfigProfile",
    call: () => cm.createConfigProfile({ name: "p" } as cm.ConfigProfileCreateRequest),
    method: "post",
    args: ["/api/v1/config-management/profiles", { name: "p" }],
  },
  {
    name: "updateConfigProfile",
    call: () => cm.updateConfigProfile("p1", { name: "q" } as cm.ConfigProfileUpdateRequest),
    method: "put",
    args: ["/api/v1/config-management/profiles/p1", { name: "q" }],
  },
  { name: "deleteConfigProfile", call: () => cm.deleteConfigProfile("p1"), method: "delete", args: ["/api/v1/config-management/profiles/p1"], returnsData: false },
  { name: "getConfigProfileVersions", call: () => cm.getConfigProfileVersions("p1"), method: "get", args: ["/api/v1/config-management/profiles/p1/versions"] },
  { name: "getConfigProfileAssignments", call: () => cm.getConfigProfileAssignments("p1"), method: "get", args: ["/api/v1/config-management/profiles/p1/assignments"] },
  { name: "getConfigMgmtEngineCatalog", call: () => cm.getConfigMgmtEngineCatalog(), method: "get", args: ["/api/v1/config-management/engines"] },
  { name: "getDriftingHosts", call: () => cm.getDriftingHosts(), method: "get", args: ["/api/v1/config-management/drift"] },
  { name: "getHostDrift", call: () => cm.getHostDrift("h1"), method: "get", args: ["/api/v1/hosts/h1/config-management/drift"] },
  {
    name: "remediateDrift",
    call: () => cm.remediateDrift("h1", "p1"),
    method: "post",
    args: ["/api/v1/config-management/drift/remediate", { host_id: "h1", profile_id: "p1" }],
  },
  { name: "getBaselineCategories", call: () => cm.getBaselineCategories(), method: "get", args: ["/api/v1/config-management/baseline-categories"] },
  {
    name: "getBaselineDiff without categories",
    call: () => cm.getBaselineDiff("h1", "ref"),
    method: "get",
    args: ["/api/v1/hosts/h1/config-management/baseline-diff", { params: { reference_host_id: "ref" } }],
  },
  {
    name: "getBaselineDiff empty categories",
    call: () => cm.getBaselineDiff("h1", "ref", []),
    method: "get",
    args: ["/api/v1/hosts/h1/config-management/baseline-diff", { params: { reference_host_id: "ref" } }],
  },
  {
    name: "getBaselineDiff with categories",
    call: () => cm.getBaselineDiff("h1", "ref", ["packages", "users"]),
    method: "get",
    args: [
      "/api/v1/hosts/h1/config-management/baseline-diff",
      { params: { reference_host_id: "ref", categories: "packages,users" } },
    ],
  },
];

const qpCases: Case[] = [
  { name: "getCatalog", call: () => qp.getCatalog(), method: "get", args: [`${QB}/catalog`] },
  { name: "getPacks", call: () => qp.getPacks(), method: "get", args: [QB] },
  { name: "getPack", call: () => qp.getPack("p1"), method: "get", args: [`${QB}/p1`] },
  { name: "createPack", call: () => qp.createPack({ name: "n", queries: [] }), method: "post", args: [QB, { name: "n", queries: [] }] },
  { name: "updatePack", call: () => qp.updatePack("p1", { enabled: false }), method: "put", args: [`${QB}/p1`, { enabled: false }] },
  { name: "deletePack", call: () => qp.deletePack("p1"), method: "delete", args: [`${QB}/p1`], returnsData: false },
  { name: "validatePack", call: () => qp.validatePack({ name: "n", queries: [] }), method: "post", args: [`${QB}/validate`, { name: "n", queries: [] }] },
  { name: "getAssignments", call: () => qp.getAssignments(), method: "get", args: [`${QB}/assignments/all`] },
  {
    name: "createAssignment",
    call: () => qp.createAssignment({ pack_id: "p1", host_id: "h1" }),
    method: "post",
    args: [`${QB}/assignments`, { pack_id: "p1", host_id: "h1" }],
  },
  { name: "deleteAssignment", call: () => qp.deleteAssignment("a1"), method: "delete", args: [`${QB}/assignments/a1`], returnsData: false },
  { name: "getRuns all", call: () => qp.getRuns(), method: "get", args: [`${QB}/runs/recent`] },
  { name: "getRuns host", call: () => qp.getRuns("h 1"), method: "get", args: [`${QB}/runs/recent?host_id=h%201`] },
  { name: "getRun", call: () => qp.getRun("r1"), method: "get", args: [`${QB}/runs/r1`] },
  { name: "createLiveQuery", call: () => qp.createLiveQuery({ sql: "select 1" }), method: "post", args: [`${QB}/live`, { sql: "select 1" }] },
  { name: "getLiveQueries", call: () => qp.getLiveQueries(), method: "get", args: [`${QB}/live`] },
  { name: "getLiveQuery", call: () => qp.getLiveQuery("l1"), method: "get", args: [`${QB}/live/l1`] },
  { name: "cancelLiveQuery", call: () => qp.cancelLiveQuery("l1"), method: "post", args: [`${QB}/live/l1/cancel`] },
];

const runCase = async (c: Case) => {
  const result = await c.call();
  expect(mocks[c.method]).toHaveBeenCalledTimes(1);
  expect(mocks[c.method]).toHaveBeenCalledWith(...c.args);
  if (c.returnsData === false) {
    expect(result).toBeUndefined();
  } else {
    expect(result).toEqual(DATA);
  }
};

beforeEach(() => {
  for (const m of Object.values(mocks)) {
    m.mockReset();
    m.mockResolvedValue({ data: DATA });
  }
});

describe("configFleetService", () => {
  test.each(fleetCases.map((c) => [c.name, c] as const))("%s", async (_n, c) => {
    await runCase(c);
  });

  test("propagates request failures", async () => {
    mocks.get.mockRejectedValueOnce(new Error("boom"));
    await expect(fleet.getInventories()).rejects.toThrow("boom");
  });
});

describe("configManagementService", () => {
  test.each(cmCases.map((c) => [c.name, c] as const))("%s", async (_n, c) => {
    await runCase(c);
  });
});

describe("queryPackService", () => {
  test.each(qpCases.map((c) => [c.name, c] as const))("%s", async (_n, c) => {
    await runCase(c);
  });
});

// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Host Detail inventory filtering.
 *
 * Pure derivation, which is why it is worth testing directly rather than
 * through the page: every branch here is a rule about what an operator sees
 * in a grid, and a wrong one is invisible until somebody asks "why is that
 * disk listed twice".
 *
 * The property this file guards hardest is that filtering does NOT MUTATE
 * its inputs. These arrays are props owned by the page; sorting one in place
 * reorders the caller's state without changing its identity, so a memo that
 * depends on it will not recompute but will quietly see different data.
 */

import { renderHook } from "@testing-library/react";
import { describe, test, expect } from "vitest";

import { useHostInventoryFilters } from "../../../Components/HostDetail/useHostInventoryFilters";

const disk = (over = {}) =>
  ({
    name: "disk0",
    mount_point: "/",
    is_physical: true,
    ...over,
  }) as never;

const iface = (over = {}) =>
  ({
    name: "eth0",
    ipv4_address: "10.0.0.1",
    ipv6_address: null,
    ...over,
  }) as never;

const user = (over = {}) =>
  ({ username: "alice", is_system_user: false, ...over }) as never;

const group = (over = {}) =>
  ({ group_name: "staff", is_system_group: false, ...over }) as never;

const args = (over = {}) =>
  ({
    host: null,
    storageDevices: [],
    networkInterfaces: [],
    userAccounts: [],
    userGroups: [],
    storageFilter: "all",
    networkFilter: "all",
    userFilter: "all",
    groupFilter: "all",
    ...over,
  }) as never;

const run = (over = {}) =>
  renderHook(() => useHostInventoryFilters(args(over))).result.current;

describe("storage deduplication", () => {
  test("devices with distinct names are all kept", () => {
    const out = run({
      storageDevices: [disk({ name: "disk0" }), disk({ name: "disk1" })],
    });
    expect(out.filteredStorageDevices).toHaveLength(2);
  });

  test("a duplicate name collapses to one entry", () => {
    // The same physical disk reported under several mounts is one disk, not
    // three rows an operator has to mentally deduplicate.
    const out = run({
      storageDevices: [
        disk({ mount_point: "/System/Volumes/Data" }),
        disk({ mount_point: "/" }),
        disk({ mount_point: "/Library/Foo" }),
      ],
    });
    expect(out.filteredStorageDevices).toHaveLength(1);
  });

  test("the root mount wins when a name is duplicated", () => {
    // Root is the one an operator recognises; showing /System/Volumes/Data
    // instead is technically true and useless.
    const out = run({
      storageDevices: [
        disk({ mount_point: "/System/Volumes/Data" }),
        disk({ mount_point: "/" }),
      ],
    });
    expect(out.filteredStorageDevices[0].mount_point).toBe("/");
  });

  test("a system volume outranks a Library volume", () => {
    const out = run({
      storageDevices: [
        disk({ mount_point: "/Library/Foo" }),
        disk({ mount_point: "/System/Volumes/Data" }),
      ],
    });
    expect(out.filteredStorageDevices[0].mount_point).toBe(
      "/System/Volumes/Data",
    );
  });

  test("an ordinary mount outranks both system and Library", () => {
    const out = run({
      storageDevices: [
        disk({ mount_point: "/System/Volumes/Data" }),
        disk({ mount_point: "/mnt/data" }),
      ],
    });
    expect(out.filteredStorageDevices[0].mount_point).toBe("/mnt/data");
  });

  test("a device with no name is still grouped, not dropped", () => {
    const out = run({
      storageDevices: [disk({ name: undefined }), disk({ name: undefined })],
    });
    expect(out.filteredStorageDevices).toHaveLength(1);
  });
});

describe("storage filtering", () => {
  const devices = [
    disk({ name: "phys", is_physical: true }),
    disk({ name: "log", is_physical: false }),
  ];

  test("physical shows only physical", () => {
    const out = run({ storageDevices: devices, storageFilter: "physical" });
    expect(out.filteredStorageDevices.map((d) => d.name)).toEqual(["phys"]);
  });

  test("logical shows only logical", () => {
    const out = run({ storageDevices: devices, storageFilter: "logical" });
    expect(out.filteredStorageDevices.map((d) => d.name)).toEqual(["log"]);
  });

  test("all sorts physical first", () => {
    const out = run({
      storageDevices: [
        disk({ name: "log", is_physical: false }),
        disk({ name: "phys", is_physical: true }),
      ],
      storageFilter: "all",
    });
    expect(out.filteredStorageDevices.map((d) => d.name)).toEqual([
      "phys",
      "log",
    ]);
  });
});

describe("network filtering", () => {
  const up = iface({ name: "up", ipv4_address: "10.0.0.1" });
  const v6 = iface({ name: "v6", ipv4_address: null, ipv6_address: "::1" });
  const down = iface({ name: "down", ipv4_address: null, ipv6_address: null });

  test("active counts an interface with only IPv6", () => {
    // IPv6-only is a real deployment; treating it as inactive would hide it.
    const out = run({ networkInterfaces: [v6], networkFilter: "active" });
    expect(out.filteredNetworkInterfaces.map((i) => i.name)).toEqual(["v6"]);
  });

  test("inactive means no address of either family", () => {
    const out = run({
      networkInterfaces: [up, v6, down],
      networkFilter: "inactive",
    });
    expect(out.filteredNetworkInterfaces.map((i) => i.name)).toEqual(["down"]);
  });

  test("all sorts addressed interfaces first", () => {
    const out = run({
      networkInterfaces: [down, up],
      networkFilter: "all",
    });
    expect(out.filteredNetworkInterfaces.map((i) => i.name)).toEqual([
      "up",
      "down",
    ]);
  });
});

describe("user and group filtering", () => {
  const sys = user({ username: "root", is_system_user: true });
  const reg = user({ username: "alice", is_system_user: false });

  test("system shows only system users", () => {
    const out = run({ userAccounts: [sys, reg], userFilter: "system" });
    expect(out.filteredUsers.map((u) => u.username)).toEqual(["root"]);
  });

  test("regular shows only regular users", () => {
    const out = run({ userAccounts: [sys, reg], userFilter: "regular" });
    expect(out.filteredUsers.map((u) => u.username)).toEqual(["alice"]);
  });

  test("all sorts regular users before system ones", () => {
    const out = run({ userAccounts: [sys, reg], userFilter: "all" });
    expect(out.filteredUsers.map((u) => u.username)).toEqual(["alice", "root"]);
  });

  test("groups filter and sort the same way", () => {
    const sysG = group({ group_name: "wheel", is_system_group: true });
    const regG = group({ group_name: "staff", is_system_group: false });
    expect(
      run({ userGroups: [sysG, regG], groupFilter: "system" }).filteredGroups.map(
        (g) => g.group_name,
      ),
    ).toEqual(["wheel"]);
    expect(
      run({ userGroups: [sysG, regG], groupFilter: "regular" }).filteredGroups.map(
        (g) => g.group_name,
      ),
    ).toEqual(["staff"]);
    expect(
      run({ userGroups: [sysG, regG], groupFilter: "all" }).filteredGroups.map(
        (g) => g.group_name,
      ),
    ).toEqual(["staff", "wheel"]);
  });
});

describe("the caller's arrays are never mutated", () => {
  // These arrays are props owned by the page. Sorting one in place reorders
  // the caller's state WITHOUT changing its identity, so a memo depending on
  // it does not recompute but silently sees different data.
  test("sorting users leaves the input order intact", () => {
    const input: { username: string }[] = [
      user({ username: "root", is_system_user: true }),
      user({ username: "alice", is_system_user: false }),
    ];
    run({ userAccounts: input, userFilter: "all" });
    expect(input.map((u) => u.username)).toEqual(["root", "alice"]);
  });

  test("sorting groups leaves the input order intact", () => {
    const input: { group_name: string }[] = [
      group({ group_name: "wheel", is_system_group: true }),
      group({ group_name: "staff", is_system_group: false }),
    ];
    run({ userGroups: input, groupFilter: "all" });
    expect(input.map((g) => g.group_name)).toEqual(["wheel", "staff"]);
  });

  test("sorting interfaces leaves the input order intact", () => {
    const input: { name: string }[] = [
      iface({ name: "down", ipv4_address: null, ipv6_address: null }),
      iface({ name: "up" }),
    ];
    run({ networkInterfaces: input, networkFilter: "all" });
    expect(input.map((i) => i.name)).toEqual(["down", "up"]);
  });
});

describe("enabled shells", () => {
  test("absent host yields no shells rather than throwing", () => {
    expect(run({ host: null }).enabledShells).toEqual([]);
  });

  test("a JSON array is parsed", () => {
    const out = run({
      host: { enabled_shells: '["/bin/sh","/bin/bash"]' } as never,
    });
    expect(out.enabledShells).toEqual(["/bin/sh", "/bin/bash"]);
  });

  test("malformed JSON degrades to empty instead of crashing the page", () => {
    const out = run({ host: { enabled_shells: "not json" } as never });
    expect(out.enabledShells).toEqual([]);
  });

  test("valid JSON that is not an array is rejected", () => {
    // The grid maps over this; an object would throw at render time.
    const out = run({ host: { enabled_shells: '{"sh":true}' } as never });
    expect(out.enabledShells).toEqual([]);
  });
});

describe("diagnostics state", () => {
  test("pending is reported as processing", () => {
    const out = run({
      host: { diagnostics_request_status: "pending" } as never,
    });
    expect(out.isDiagnosticsProcessing).toBe(true);
  });

  test("any other status is not processing", () => {
    expect(
      run({ host: { diagnostics_request_status: "completed" } as never })
        .isDiagnosticsProcessing,
    ).toBe(false);
    expect(run({ host: null }).isDiagnosticsProcessing).toBe(false);
  });
});

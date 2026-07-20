// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { SysManageHost } from '../Services/hosts';

/** Check whether a host qualifies as a virtualization parent. */
export function isParentHost(host: SysManageHost): boolean {
    if (host.parent_host_id) return false;
    if (!host.virtualization_capabilities) return false;
    try {
        const caps = JSON.parse(host.virtualization_capabilities);
        return !!(caps.lxd?.initialized || caps.wsl?.enabled || caps.vmm?.running);
    } catch {
        return false;
    }
}

/** Sort hosts so children are grouped directly below their parent. */
export function sortHostsGrouped(hosts: SysManageHost[]): SysManageHost[] {
    const topLevelHosts = hosts
        .filter(h => !h.parent_host_id)
        .sort((a, b) => (a.fqdn || '').localeCompare(b.fqdn || ''));

    const childrenByParent = new Map<string, SysManageHost[]>();
    for (const child of hosts.filter(h => !!h.parent_host_id)) {
        const parentId = child.parent_host_id!;
        if (!childrenByParent.has(parentId)) {
            childrenByParent.set(parentId, []);
        }
        childrenByParent.get(parentId)!.push(child);
    }

    childrenByParent.forEach(children => {
        children.sort((a, b) => (a.fqdn || '').localeCompare(b.fqdn || ''));
    });

    const sorted: SysManageHost[] = [];
    for (const parent of topLevelHosts) {
        sorted.push(parent);
        const children = childrenByParent.get(parent.id);
        if (children) {
            sorted.push(...children);
            childrenByParent.delete(parent.id);
        }
    }

    childrenByParent.forEach(children => {
        sorted.push(...children);
    });

    return sorted;
}

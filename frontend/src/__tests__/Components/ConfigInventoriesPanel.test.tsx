// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Inventories.
 *
 * The preview is the reason this panel exists in the form it does. An
 * inventory RESOLVES at launch rather than storing a host list, so "who am I
 * about to change" is a question only the server can answer — and it is the
 * one to answer before pressing a button that touches four thousand machines.
 *
 * An inventory that currently resolves to nothing is called out loudly, for
 * the same reason the engine refuses to create one: a job over zero hosts
 * reports a clean success, which reads as "the fleet is converged".
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
  let s = typeof fallback === "string" ? fallback : key;
  if (opts) {
    for (const [k, v] of Object.entries(opts)) {
      s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
    }
  }
  return s;
};
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("../../Services/configFleetService", () => ({
  getInventories: vi.fn(),
  createInventory: vi.fn(),
  deleteInventory: vi.fn(),
  previewInventory: vi.fn(),
}));

import {
  getInventories,
  createInventory,
  deleteInventory,
  previewInventory,
} from "../../Services/configFleetService";
import ConfigInventoriesPanel from "../../Components/ConfigInventoriesPanel";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const inventory = (over = {}) => ({
  id: "i1",
  name: "web tier",
  description: "front-end fleet",
  all_hosts: false,
  host_count: 12,
  created_by: "op",
  updated_by: "op",
  created_at: null,
  updated_at: null,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  m(getInventories).mockResolvedValue([inventory()]);
  m(previewInventory).mockResolvedValue(["web01.invalid", "web02.invalid"]);
});

describe("ConfigInventoriesPanel", () => {
  test("the host count is shown so the blast radius is visible at a glance", async () => {
    render(<ConfigInventoriesPanel canEdit />);
    expect(await screen.findByText("12 hosts")).toBeInTheDocument();
  });

  test("an every-host inventory is marked as such", async () => {
    // "The entire fleet" is a different and more dangerous statement than any
    // selector, and it should read as one.
    m(getInventories).mockResolvedValue([inventory({ all_hosts: true })]);
    render(<ConfigInventoriesPanel canEdit />);
    expect(await screen.findByText("Every host")).toBeInTheDocument();
  });

  test("the preview names the actual hosts", async () => {
    render(<ConfigInventoriesPanel canEdit />);
    fireEvent.click(await screen.findByText("Preview"));
    expect(await screen.findByText("web01.invalid")).toBeInTheDocument();
    expect(screen.getByText("web02.invalid")).toBeInTheDocument();
  });

  test("an inventory that resolves to nothing warns rather than showing an empty list", async () => {
    m(previewInventory).mockResolvedValue([]);
    render(<ConfigInventoriesPanel canEdit />);
    fireEvent.click(await screen.findByText("Preview"));
    expect(
      await screen.findByText(/currently selects no active hosts/i),
    ).toBeInTheDocument();
  });

  test("creating sends what was typed", async () => {
    m(createInventory).mockResolvedValue(inventory());
    render(<ConfigInventoriesPanel canEdit />);
    fireEvent.click(await screen.findByText("New inventory"));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "db tier" },
    });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() =>
      expect(createInventory).toHaveBeenCalledWith(
        expect.objectContaining({ name: "db tier", all_hosts: false }),
      ),
    );
  });

  test("deleting asks first and names what it would remove", async () => {
    render(<ConfigInventoriesPanel canEdit />);
    fireEvent.click(await screen.findByText("Delete"));
    expect(
      await screen.findByText(/Job templates that use web tier/i),
    ).toBeInTheDocument();
  });

  test("a refused delete shows the server's reason", async () => {
    // The 409 detail says how many templates still use it, which is more
    // useful than anything this component could invent.
    m(deleteInventory).mockRejectedValue({
      response: { data: { detail: "This inventory is used by 2 job template(s)" } },
    });
    render(<ConfigInventoriesPanel canEdit />);
    fireEvent.click(await screen.findByText("Delete"));
    fireEvent.click(screen.getAllByText("Delete")[1]);
    expect(
      await screen.findByText("This inventory is used by 2 job template(s)"),
    ).toBeInTheDocument();
  });

  test("without the edit permission nothing can be created or deleted", async () => {
    render(<ConfigInventoriesPanel canEdit={false} />);
    await screen.findByText("web tier");
    expect(screen.queryByText("New inventory")).not.toBeInTheDocument();
    expect(screen.queryByText("Delete")).not.toBeInTheDocument();
  });

  test("an empty list explains what an inventory is for", async () => {
    m(getInventories).mockResolvedValue([]);
    render(<ConfigInventoriesPanel canEdit />);
    expect(
      await screen.findByText(/names the hosts a fleet job runs against/i),
    ).toBeInTheDocument();
  });
});

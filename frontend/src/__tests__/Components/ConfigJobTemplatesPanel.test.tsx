// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Job templates.
 *
 * Two behaviors here are safety rails rather than features.
 *
 * **Dry run is the default.** The first thing anybody should do with a new
 * template is find out what it WOULD change. Defaulting a fleet-wide run to
 * live is the one mistake this page can make that cannot be undone.
 *
 * **The launch dialog names the subject.** Profile, inventory, and whether it
 * is live -- "are you sure?" without a subject is a speed bump, not a check.
 */

import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
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
  getJobTemplates: vi.fn(),
  getInventories: vi.fn(),
  createJobTemplate: vi.fn(),
  deleteJobTemplate: vi.fn(),
  launchJobTemplate: vi.fn(),
}));
vi.mock("../../Services/configManagementService", () => ({
  getConfigProfiles: vi.fn(),
}));

import {
  getJobTemplates,
  getInventories,
  createJobTemplate,
  launchJobTemplate,
} from "../../Services/configFleetService";
import { getConfigProfiles } from "../../Services/configManagementService";
import ConfigJobTemplatesPanel from "../../Components/ConfigJobTemplatesPanel";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

/** Choose an option from a MUI select by its visible label. */
const pickOption = async (label: string, option: string) => {
  fireEvent.mouseDown(screen.getByLabelText(label));
  const listbox = await screen.findByRole("listbox");
  fireEvent.click(within(listbox).getByText(option));
};


const template = (over = {}) => ({
  id: "t1",
  name: "nightly baseline",
  description: null,
  profile_id: "p1",
  inventory_id: "i1",
  check_mode: true,
  concurrency: 20,
  timeout_seconds: null,
  schedule: "0 3 * * *",
  enabled: true,
  created_by: "op",
  updated_by: "op",
  created_at: null,
  updated_at: null,
  last_launched_at: null,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  m(getJobTemplates).mockResolvedValue([template()]);
  m(getInventories).mockResolvedValue([
    { id: "i1", name: "web tier", description: null, all_hosts: false, host_count: 12,
      created_by: null, updated_by: null, created_at: null, updated_at: null },
  ]);
  m(getConfigProfiles).mockResolvedValue([
    { id: "p1", name: "baseline", engine: "ansible-core", content: "", version: 1,
      is_active: true, description: null, created_by: null, updated_by: null,
      created_at: null, updated_at: null },
  ]);
});

describe("ConfigJobTemplatesPanel", () => {
  test("a template shows what it runs against what", async () => {
    render(<ConfigJobTemplatesPanel canEdit canLaunch />);
    expect(await screen.findByText(/baseline.*web tier/)).toBeInTheDocument();
  });

  test("the concurrency is shown so the wave size is never a mystery", async () => {
    render(<ConfigJobTemplatesPanel canEdit canLaunch />);
    expect(await screen.findByText("20 hosts at once")).toBeInTheDocument();
  });

  test("a live launch warns that it changes hosts for real", async () => {
    m(getJobTemplates).mockResolvedValue([template({ check_mode: false })]);
    render(<ConfigJobTemplatesPanel canEdit canLaunch />);
    fireEvent.click(await screen.findByText("Launch"));
    expect(
      await screen.findByText(/runs baseline for real on every host in web tier/i),
    ).toBeInTheDocument();
  });

  test("a dry-run launch says plainly that nothing will change", async () => {
    render(<ConfigJobTemplatesPanel canEdit canLaunch />);
    fireEvent.click(await screen.findByText("Launch"));
    expect(
      await screen.findByText(/as a dry run. Nothing will be changed/i),
    ).toBeInTheDocument();
  });

  test("launching reports how many hosts it reached", async () => {
    m(launchJobTemplate).mockResolvedValue({ id: "j1", total_targets: 412 });
    render(<ConfigJobTemplatesPanel canEdit canLaunch />);
    fireEvent.click(await screen.findByText("Launch"));
    fireEvent.click(screen.getAllByText("Launch")[1]);
    expect(
      await screen.findByText(/Launched against 412 hosts/i),
    ).toBeInTheDocument();
  });

  test("a clamped concurrency is reported rather than silently accepted", async () => {
    // The server caps it; saying so is the only way an operator learns the
    // ceiling exists instead of believing they got 10,000 and wondering why
    // the fleet is converging slowly.
    m(createJobTemplate).mockResolvedValue(template({ concurrency: 500 }));
    render(<ConfigJobTemplatesPanel canEdit canLaunch />);
    fireEvent.click(await screen.findByText("New job template"));

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "wide" } });
    fireEvent.change(screen.getByLabelText("Hosts at a time"), {
      target: { value: "10000" },
    });
    await pickOption("Profile", "baseline");
    await pickOption("Inventory", "web tier");

    fireEvent.click(screen.getByText("Save"));
    expect(
      await screen.findByText(/adjusted to 500, the highest this server allows/i),
    ).toBeInTheDocument();
  });

  test("what was typed is sent, and what came back is what is shown", async () => {
    m(createJobTemplate).mockResolvedValue(template({ concurrency: 7 }));
    render(<ConfigJobTemplatesPanel canEdit canLaunch />);
    fireEvent.click(await screen.findByText("New job template"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "slow" } });
    fireEvent.change(screen.getByLabelText("Hosts at a time"), {
      target: { value: "7" },
    });
    await pickOption("Profile", "baseline");
    await pickOption("Inventory", "web tier");
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(createJobTemplate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "slow",
          profile_id: "p1",
          inventory_id: "i1",
          concurrency: 7,
          // Dry run is the DEFAULT for a fleet template: a live run across an
          // inventory is the one mistake here that cannot be undone.
          check_mode: true,
        }),
      ),
    );
    // No clamp notice when the server honored the request.
    expect(screen.queryByText(/adjusted to/i)).not.toBeInTheDocument();
  });

  test("without the launch permission there is no launch button", async () => {
    render(<ConfigJobTemplatesPanel canEdit canLaunch={false} />);
    await screen.findByText("nightly baseline");
    expect(screen.queryByText("Launch")).not.toBeInTheDocument();
  });

  test("without the edit permission there is no create button", async () => {
    render(<ConfigJobTemplatesPanel canEdit={false} canLaunch />);
    await screen.findByText("nightly baseline");
    expect(screen.queryByText("New job template")).not.toBeInTheDocument();
  });

  test("creating is impossible until a profile and an inventory exist", async () => {
    // A disabled button with the empty-state text beside it beats a form that
    // cannot be submitted.
    m(getConfigProfiles).mockResolvedValue([]);
    m(getJobTemplates).mockResolvedValue([]);
    render(<ConfigJobTemplatesPanel canEdit canLaunch />);
    await waitFor(() =>
      expect(screen.getByText("New job template")).toBeDisabled(),
    );
  });

  test("a failure to load says so instead of rendering an empty page", async () => {
    m(getJobTemplates).mockRejectedValue({
      response: { data: { detail: "not licensed" } },
    });
    render(<ConfigJobTemplatesPanel canEdit canLaunch />);
    expect(await screen.findByText("not licensed")).toBeInTheDocument();
  });
});

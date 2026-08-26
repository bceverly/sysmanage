// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- see UserDetail.test.tsx.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

// The real DataGrid's CSS-var shorthand trips jsdom's cssstyle, and this test
// is about the settings panel rather than grid internals.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({ rows }: { rows?: Array<{ id: string; name?: string }> }) => (
    <div data-testid="grid">
      {(rows ?? []).map((r) => (
        <div key={r.id}>{r.name}</div>
      ))}
    </div>
  ),
}));

vi.mock("../../Services/reportTemplates", () => ({
  reportTemplatesService: {
    list: vi.fn(),
    baseTypes: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    fieldsFor: vi.fn(),
  },
}));

import { reportTemplatesService } from "../../Services/reportTemplates";
import ReportTemplatesSettings from "../../Components/ReportTemplatesSettings";

const TEMPLATE = {
  id: "t1",
  name: "Nightly hosts",
  description: "every host",
  base_report_type: "hosts",
  selected_fields: ["fqdn"],
  enabled: true,
  created_at: null,
  updated_at: null,
};

const FIELDS = {
  base_report_type: "hosts",
  fields: [
    { code: "fqdn", label: "FQDN" },
    { code: "os", label: "Operating System" },
  ],
};

describe("ReportTemplatesSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(reportTemplatesService.list).mockResolvedValue([TEMPLATE]);
    vi.mocked(reportTemplatesService.baseTypes).mockResolvedValue([
      "hosts",
      "users",
    ]);
    vi.mocked(reportTemplatesService.fieldsFor).mockResolvedValue(FIELDS);
    vi.mocked(reportTemplatesService.create).mockResolvedValue(TEMPLATE);
    vi.mocked(reportTemplatesService.update).mockResolvedValue(TEMPLATE);
    vi.mocked(reportTemplatesService.remove).mockResolvedValue(undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  test("lists the existing templates", async () => {
    render(<ReportTemplatesSettings />);
    expect(await screen.findByText("Nightly hosts")).toBeInTheDocument();
  });

  test("renders the empty state when there are none", async () => {
    vi.mocked(reportTemplatesService.list).mockResolvedValue([]);
    render(<ReportTemplatesSettings />);
    expect(
      await screen.findByText("No report templates defined yet."),
    ).toBeInTheDocument();
  });

  test("reports a load failure", async () => {
    vi.mocked(reportTemplatesService.list).mockRejectedValue(new Error("down"));
    render(<ReportTemplatesSettings />);
    expect(
      await screen.findByText("Failed to load report templates"),
    ).toBeInTheDocument();
  });

  test("the add dialog preloads fields for the first base type", async () => {
    render(<ReportTemplatesSettings />);
    await screen.findByText("Nightly hosts");
    fireEvent.click(screen.getByRole("button", { name: "Add Template" }));
    expect(
      await screen.findByText("Add Report Template"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(reportTemplatesService.fieldsFor).toHaveBeenCalledWith("hosts"),
    );
  });

  test("a nameless template is refused before any request", async () => {
    render(<ReportTemplatesSettings />);
    await screen.findByText("Nightly hosts");
    fireEvent.click(screen.getByRole("button", { name: "Add Template" }));
    await screen.findByText("Add Report Template");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    expect(reportTemplatesService.create).not.toHaveBeenCalled();
  });

  test("a whitespace-only name counts as nameless", async () => {
    render(<ReportTemplatesSettings />);
    await screen.findByText("Nightly hosts");
    fireEvent.click(screen.getByRole("button", { name: "Add Template" }));
    await screen.findByText("Add Report Template");
    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    expect(reportTemplatesService.create).not.toHaveBeenCalled();
  });

  test("a template with no fields selected is refused", async () => {
    render(<ReportTemplatesSettings />);
    await screen.findByText("Nightly hosts");
    fireEvent.click(screen.getByRole("button", { name: "Add Template" }));
    await screen.findByText("Add Report Template");
    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: "New one" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText("Select at least one field"),
    ).toBeInTheDocument();
    expect(reportTemplatesService.create).not.toHaveBeenCalled();
  });

  test("creating a valid template posts it and reports success", async () => {
    render(<ReportTemplatesSettings />);
    await screen.findByText("Nightly hosts");
    fireEvent.click(screen.getByRole("button", { name: "Add Template" }));
    await screen.findByText("Add Report Template");
    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: "New one" },
    });
    fireEvent.click(await screen.findByLabelText("FQDN (fqdn)"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(reportTemplatesService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "New one",
          base_report_type: "hosts",
          selected_fields: ["fqdn"],
        }),
      ),
    );
    expect(await screen.findByText("Template created")).toBeInTheDocument();
  });

  test("surfaces the server's detail when a save is refused", async () => {
    vi.mocked(reportTemplatesService.create).mockRejectedValue({
      response: { data: { detail: "name already taken" } },
    });
    render(<ReportTemplatesSettings />);
    await screen.findByText("Nightly hosts");
    fireEvent.click(screen.getByRole("button", { name: "Add Template" }));
    await screen.findByText("Add Report Template");
    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: "New one" },
    });
    fireEvent.click(await screen.findByLabelText("FQDN (fqdn)"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("name already taken")).toBeInTheDocument();
  });

  test("cancelling the dialog writes nothing", async () => {
    render(<ReportTemplatesSettings />);
    await screen.findByText("Nightly hosts");
    fireEvent.click(screen.getByRole("button", { name: "Add Template" }));
    await screen.findByText("Add Report Template");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.queryByText("Add Report Template")).not.toBeInTheDocument(),
    );
    expect(reportTemplatesService.create).not.toHaveBeenCalled();
  });

  test("changing the base type reloads its fields and clears the selection", async () => {
    render(<ReportTemplatesSettings />);
    await screen.findByText("Nightly hosts");
    fireEvent.click(screen.getByRole("button", { name: "Add Template" }));
    await screen.findByText("Add Report Template");
    fireEvent.click(await screen.findByLabelText("FQDN (fqdn)"));
    vi.mocked(reportTemplatesService.fieldsFor).mockClear();
    fireEvent.mouseDown(screen.getByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "users" }));
    await waitFor(() =>
      expect(reportTemplatesService.fieldsFor).toHaveBeenCalledWith("users"),
    );
    // The previously ticked field belonged to the old base type.
    expect(screen.getByLabelText("FQDN (fqdn)")).not.toBeChecked();
  });

  test("a fields lookup failure leaves the list empty rather than crashing", async () => {
    vi.mocked(reportTemplatesService.fieldsFor).mockRejectedValue(
      new Error("down"),
    );
    render(<ReportTemplatesSettings />);
    await screen.findByText("Nightly hosts");
    fireEvent.click(screen.getByRole("button", { name: "Add Template" }));
    expect(await screen.findByText("Add Report Template")).toBeInTheDocument();
    expect(screen.queryByLabelText("FQDN (fqdn)")).not.toBeInTheDocument();
  });
});

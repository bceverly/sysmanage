// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- see UserDetail.test.tsx.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/reportBranding", () => ({
  reportBrandingService: {
    get: vi.fn(),
    update: vi.fn(),
    uploadLogo: vi.fn(),
    deleteLogo: vi.fn(),
    fetchLogoObjectUrl: vi.fn(),
  },
}));

import { reportBrandingService } from "../../Services/reportBranding";
import ReportBrandingSettings from "../../Components/ReportBrandingSettings";

const BRANDING = {
  company_name: "Acme",
  header_text: "Confidential",
  has_logo: false,
  logo_mime_type: null,
  updated_at: null,
};
const WITH_LOGO = {
  ...BRANDING,
  has_logo: true,
  logo_mime_type: "image/png",
};

describe("ReportBrandingSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(reportBrandingService.get).mockResolvedValue(BRANDING);
    vi.mocked(reportBrandingService.update).mockResolvedValue(BRANDING);
    vi.mocked(reportBrandingService.uploadLogo).mockResolvedValue(WITH_LOGO);
    vi.mocked(reportBrandingService.deleteLogo).mockResolvedValue(BRANDING);
    vi.mocked(reportBrandingService.fetchLogoObjectUrl).mockResolvedValue(null);
    vi.spyOn(globalThis.console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  test("loads the current branding into the form", async () => {
    render(<ReportBrandingSettings />);
    await waitFor(() =>
      expect(screen.getByLabelText(/^Company Name/)).toHaveValue("Acme"),
    );
    expect(screen.getByLabelText(/^Header Text/)).toHaveValue("Confidential");
  });

  test("reports a load failure", async () => {
    vi.mocked(reportBrandingService.get).mockRejectedValue(new Error("down"));
    render(<ReportBrandingSettings />);
    expect(
      await screen.findByText("Failed to load report branding"),
    ).toBeInTheDocument();
  });

  test("shows the no-logo placeholder when none is set", async () => {
    render(<ReportBrandingSettings />);
    expect(await screen.findByText("No logo set")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Upload Logo" }),
    ).toBeInTheDocument();
  });

  test("offers replace and remove once a logo exists", async () => {
    vi.mocked(reportBrandingService.get).mockResolvedValue(WITH_LOGO);
    vi.mocked(reportBrandingService.fetchLogoObjectUrl).mockResolvedValue(
      "blob:logo",
    );
    render(<ReportBrandingSettings />);
    expect(
      await screen.findByRole("button", { name: "Replace Logo" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Remove Logo" }),
    ).toBeInTheDocument();
  });

  test("saving sends the edited fields", async () => {
    render(<ReportBrandingSettings />);
    await waitFor(() =>
      expect(screen.getByLabelText(/^Company Name/)).toHaveValue("Acme"),
    );
    fireEvent.change(screen.getByLabelText(/^Company Name/), {
      target: { value: "Globex" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(reportBrandingService.update).toHaveBeenCalledWith(
        expect.objectContaining({ company_name: "Globex" }),
      ),
    );
    expect(await screen.findByText("Branding saved")).toBeInTheDocument();
  });

  test("surfaces the server's detail when a save is refused", async () => {
    vi.mocked(reportBrandingService.update).mockRejectedValue({
      response: { data: { detail: "name too long" } },
    });
    render(<ReportBrandingSettings />);
    await waitFor(() =>
      expect(screen.getByLabelText(/^Company Name/)).toHaveValue("Acme"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("name too long")).toBeInTheDocument();
  });

  test("choosing a file uploads it", async () => {
    render(<ReportBrandingSettings />);
    await screen.findByText("No logo set");
    const file = new globalThis.File(["png"], "logo.png", { type: "image/png" });
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() =>
      expect(reportBrandingService.uploadLogo).toHaveBeenCalledWith(file),
    );
    expect(await screen.findByText("Logo uploaded")).toBeInTheDocument();
  });

  test("a rejected upload is reported", async () => {
    vi.mocked(reportBrandingService.uploadLogo).mockRejectedValue({
      response: { data: { detail: "not an image" } },
    });
    render(<ReportBrandingSettings />);
    await screen.findByText("No logo set");
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new globalThis.File(["x"], "a.txt", { type: "text/plain" })] },
    });
    expect(await screen.findByText("not an image")).toBeInTheDocument();
  });

  test("choosing no file uploads nothing", async () => {
    render(<ReportBrandingSettings />);
    await screen.findByText("No logo set");
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [] } });
    await waitFor(() =>
      expect(reportBrandingService.uploadLogo).not.toHaveBeenCalled(),
    );
  });

  test("removing a logo asks for confirmation first", async () => {
    vi.mocked(reportBrandingService.get).mockResolvedValue(WITH_LOGO);
    const confirm = vi
      .spyOn(globalThis, "confirm")
      .mockReturnValue(false);
    render(<ReportBrandingSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Logo" }));
    expect(confirm).toHaveBeenCalledWith("Remove the current logo?");
    // Declining must not delete anything.
    expect(reportBrandingService.deleteLogo).not.toHaveBeenCalled();
  });

  test("confirming the removal deletes the logo", async () => {
    vi.mocked(reportBrandingService.get).mockResolvedValue(WITH_LOGO);
    vi.spyOn(globalThis, "confirm").mockReturnValue(true);
    render(<ReportBrandingSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Logo" }));
    await waitFor(() =>
      expect(reportBrandingService.deleteLogo).toHaveBeenCalled(),
    );
    expect(await screen.findByText("Logo removed")).toBeInTheDocument();
  });

  test("a failed removal is reported", async () => {
    vi.mocked(reportBrandingService.get).mockResolvedValue(WITH_LOGO);
    vi.spyOn(globalThis, "confirm").mockReturnValue(true);
    vi.mocked(reportBrandingService.deleteLogo).mockRejectedValue(
      new Error("locked"),
    );
    render(<ReportBrandingSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Logo" }));
    expect(await screen.findByText("Failed to remove logo")).toBeInTheDocument();
  });
});

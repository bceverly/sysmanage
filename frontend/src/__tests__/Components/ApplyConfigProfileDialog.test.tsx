// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The apply-profile dialog (Phase 20.1).
 *
 * This form runs arbitrary code as root on a managed host, so the property
 * that matters most is that **dry run is the default**: the safe option is the
 * one you get by not thinking about it, and making real changes has to be a
 * deliberate act. Several tests pin that rather than trusting the initial
 * state to survive a refactor.
 *
 * The second property is that the SERVER's error detail wins. It is the only
 * thing that names which field a mismatched host actually wants, so replacing
 * it with a generic message would throw away the useful half of the failure.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/configManagementService", () => ({
  applyConfigProfile: vi.fn(),
}));

import { applyConfigProfile } from "../../Services/configManagementService";
import ApplyConfigProfileDialog from "../../Components/ApplyConfigProfileDialog";

const base = {
  open: true,
  hostId: "h1",
  executor: "ansible-core",
  onClose: vi.fn(),
};

/** The dry-run toggle, found the way a user finds it: by its label. */
const dryRunToggle = () =>
  screen.getByLabelText("Dry run (report changes without making them)");

const typeBody = (text: string) => {
  const field = screen.getByLabelText(/Playbook content|DSC resources/);
  fireEvent.change(field, { target: { value: text } });
};

describe("ApplyConfigProfileDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(applyConfigProfile).mockResolvedValue({
      host_id: "h1",
      queued: true,
      check_mode: true,
      message: "ok",
    });
  });
  afterEach(() => vi.restoreAllMocks());

  test("dry run is on by default and the action says so", () => {
    render(<ApplyConfigProfileDialog {...base} />);
    expect(dryRunToggle()).toBeChecked();
    expect(screen.getByText("Preview changes")).toBeInTheDocument();
  });

  test("a dry run sends check_mode true", async () => {
    render(<ApplyConfigProfileDialog {...base} />);
    typeBody("- hosts: localhost");
    fireEvent.click(screen.getByText("Preview changes"));
    await waitFor(() =>
      expect(applyConfigProfile).toHaveBeenCalledWith("h1", {
        playbook: "- hosts: localhost",
        check_mode: true,
      }),
    );
  });

  test("turning dry run off warns before anything is sent", () => {
    render(<ApplyConfigProfileDialog {...base} />);
    fireEvent.click(dryRunToggle());
    expect(
      screen.getByText("This will make real changes to this host."),
    ).toBeInTheDocument();
    expect(screen.getByText("Apply")).toBeInTheDocument();
    expect(applyConfigProfile).not.toHaveBeenCalled();
  });

  test("a live apply sends check_mode false", async () => {
    render(<ApplyConfigProfileDialog {...base} />);
    typeBody("- hosts: localhost");
    fireEvent.click(dryRunToggle());
    fireEvent.click(screen.getByText("Apply"));
    await waitFor(() =>
      expect(applyConfigProfile).toHaveBeenCalledWith("h1", {
        playbook: "- hosts: localhost",
        check_mode: false,
      }),
    );
  });

  test("an empty body cannot be submitted", () => {
    render(<ApplyConfigProfileDialog {...base} />);
    expect(
      screen.getByText("Preview changes").closest("button"),
    ).toBeDisabled();
  });

  test("whitespace alone still counts as empty", () => {
    render(<ApplyConfigProfileDialog {...base} />);
    typeBody("   \n  ");
    expect(
      screen.getByText("Preview changes").closest("button"),
    ).toBeDisabled();
  });

  test("an optional profile name is included when given", async () => {
    render(<ApplyConfigProfileDialog {...base} />);
    typeBody("- hosts: localhost");
    fireEvent.change(screen.getByLabelText("Profile name (optional)"), {
      target: { value: "  baseline  " },
    });
    fireEvent.click(screen.getByText("Preview changes"));
    await waitFor(() =>
      expect(applyConfigProfile).toHaveBeenCalledWith("h1", {
        playbook: "- hosts: localhost",
        profile_name: "baseline",
        check_mode: true,
      }),
    );
  });

  test("a DSC host is asked for resources and sends them parsed", async () => {
    render(<ApplyConfigProfileDialog {...base} executor="dsc" />);
    typeBody('[{"name":"n","type":"T"}]');
    fireEvent.click(screen.getByText("Preview changes"));
    await waitFor(() =>
      expect(applyConfigProfile).toHaveBeenCalledWith("h1", {
        resources: [{ name: "n", type: "T" }],
        check_mode: true,
      }),
    );
  });

  test("malformed DSC JSON is caught locally, not sent", async () => {
    render(<ApplyConfigProfileDialog {...base} executor="dsc" />);
    typeBody("{not json");
    fireEvent.click(screen.getByText("Preview changes"));
    expect(
      await screen.findByText(
        "The resources must be a JSON array of DSC resource objects.",
      ),
    ).toBeInTheDocument();
    expect(applyConfigProfile).not.toHaveBeenCalled();
  });

  test("DSC resources that are not an array are rejected", async () => {
    render(<ApplyConfigProfileDialog {...base} executor="dsc" />);
    typeBody('{"name":"n"}');
    fireEvent.click(screen.getByText("Preview changes"));
    expect(
      await screen.findByText(
        "The resources must be a JSON array of DSC resource objects.",
      ),
    ).toBeInTheDocument();
    expect(applyConfigProfile).not.toHaveBeenCalled();
  });

  test("the server's own detail is shown, not a generic message", async () => {
    // The server names the field a mismatched host wants; a generic message
    // would throw that away.
    vi.mocked(applyConfigProfile).mockRejectedValue({
      response: { data: { detail: "This host uses DSC; provide 'resources'" } },
    });
    render(<ApplyConfigProfileDialog {...base} />);
    typeBody("- hosts: localhost");
    fireEvent.click(screen.getByText("Preview changes"));
    expect(
      await screen.findByText("This host uses DSC; provide 'resources'"),
    ).toBeInTheDocument();
  });

  test("a failure without a detail still reports something", async () => {
    vi.mocked(applyConfigProfile).mockRejectedValue(new Error("network"));
    render(<ApplyConfigProfileDialog {...base} />);
    typeBody("- hosts: localhost");
    fireEvent.click(screen.getByText("Preview changes"));
    expect(
      await screen.findByText("Failed to queue the configuration profile"),
    ).toBeInTheDocument();
  });

  test("a successful apply closes the dialog and notifies the caller", async () => {
    const onClose = vi.fn();
    const onApplied = vi.fn();
    render(
      <ApplyConfigProfileDialog
        {...base}
        onClose={onClose}
        onApplied={onApplied}
      />,
    );
    typeBody("- hosts: localhost");
    fireEvent.click(screen.getByText("Preview changes"));
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  test("a failed apply keeps the dialog open so the body is not lost", async () => {
    const onClose = vi.fn();
    vi.mocked(applyConfigProfile).mockRejectedValue(new Error("network"));
    render(<ApplyConfigProfileDialog {...base} onClose={onClose} />);
    typeBody("- hosts: localhost");
    fireEvent.click(screen.getByText("Preview changes"));
    await screen.findByText("Failed to queue the configuration profile");
    expect(onClose).not.toHaveBeenCalled();
  });
});

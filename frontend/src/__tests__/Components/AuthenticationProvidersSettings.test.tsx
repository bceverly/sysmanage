// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k: string, f?: string) => f || k,
    i18n: { language: "en" },
  }),
}));

vi.mock("../../Services/externalIdp", () => ({
  listProviders: vi.fn(),
  getIdpSettings: vi.fn(),
  createProvider: vi.fn(),
  updateProvider: vi.fn(),
  deleteProvider: vi.fn(),
  listRoleMappings: vi.fn(),
  createRoleMapping: vi.fn(),
  deleteRoleMapping: vi.fn(),
  updateIdpSettings: vi.fn(),
}));

import {
  listProviders,
  getIdpSettings,
  createProvider,
  deleteProvider,
  updateIdpSettings,
  listRoleMappings,
} from "../../Services/externalIdp";
import AuthenticationProvidersSettings from "../../Components/AuthenticationProvidersSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const provider = {
  id: "p1",
  name: "Corp LDAP",
  type: "ldap" as const,
  enabled: true,
  ldap_server_url: "ldaps://ldap.example.com",
};

const settings = { local_account_fallback: true, max_failed_attempts: 5 };

beforeEach(() => {
  vi.clearAllMocks();
  m(listProviders).mockResolvedValue([provider]);
  m(getIdpSettings).mockResolvedValue(settings);
  m(createProvider).mockResolvedValue(provider);
  m(deleteProvider).mockResolvedValue(undefined);
  m(updateIdpSettings).mockResolvedValue(settings);
  m(listRoleMappings).mockResolvedValue([]);
});

test("renders providers and settings after load", async () => {
  render(<AuthenticationProvidersSettings />);
  expect(await screen.findByText("Corp LDAP")).toBeInTheDocument();
  expect(listProviders).toHaveBeenCalled();
  expect(getIdpSettings).toHaveBeenCalled();
  expect(screen.getByText("Authentication Settings")).toBeInTheDocument();
});

test("opens the create dialog and creates a provider", async () => {
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");

  fireEvent.click(screen.getByRole("button", { name: /Add Provider/ }));
  const nameField = await screen.findByLabelText(/Display name/);
  fireEvent.change(nameField, { target: { value: "New IdP" } });

  const saveButtons = screen.getAllByRole("button", { name: /^Save$/ });
  fireEvent.click(saveButtons[saveButtons.length - 1]);

  await waitFor(() => expect(createProvider).toHaveBeenCalled());
});

test("saves cross-provider settings", async () => {
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");

  const saveButtons = screen.getAllByRole("button", { name: /^Save$/ });
  fireEvent.click(saveButtons[0]);
  await waitFor(() => expect(updateIdpSettings).toHaveBeenCalled());
});

test("deletes a provider after confirm", async () => {
  const confirmSpy = vi
    .spyOn(globalThis, "confirm")
    .mockReturnValue(true);
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");

  fireEvent.click(screen.getByTitle("Delete"));
  await waitFor(() => expect(deleteProvider).toHaveBeenCalledWith("p1"));
  confirmSpy.mockRestore();
});

test("opens role mappings dialog", async () => {
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");

  fireEvent.click(screen.getByTitle("Role mappings"));
  await waitFor(() => expect(listRoleMappings).toHaveBeenCalledWith("p1"));
});

test("shows an error alert when the load fails", async () => {
  m(listProviders).mockRejectedValue(new Error("boom"));
  m(getIdpSettings).mockRejectedValue(new Error("boom"));
  render(<AuthenticationProvidersSettings />);
  expect(
    await screen.findByText(/Could not load Identity Providers/),
  ).toBeInTheDocument();
});

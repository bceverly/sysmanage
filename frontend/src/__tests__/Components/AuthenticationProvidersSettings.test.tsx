// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
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
  updateProvider,
  deleteProvider,
  updateIdpSettings,
  listRoleMappings,
  createRoleMapping,
  deleteRoleMapping,
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

// ---------------------------------------------------------------------------
// Provider dialog per protocol, edit flows, settings edits, role mappings
// and failure paths.
// ---------------------------------------------------------------------------

const type = (label: RegExp, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

const dialogSave = () => {
  const saves = screen.getAllByRole("button", { name: /^Save$/ });
  fireEvent.click(saves[saves.length - 1]);
};

const openAddDialog = async () => {
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");
  fireEvent.click(screen.getByRole("button", { name: /Add Provider/ }));
  return screen.findByRole("dialog");
};

const chooseType = async (dialog: HTMLElement, label: string) => {
  fireEvent.mouseDown(within(dialog).getByRole("combobox"));
  const listbox = await screen.findByRole("listbox");
  fireEvent.click(within(listbox).getByRole("option", { name: label }));
};

test("lists each provider type with its endpoint and enabled state", async () => {
  m(listProviders).mockResolvedValue([
    provider,
    {
      id: "p2",
      name: "Okta",
      type: "oidc",
      enabled: false,
      oidc_issuer_url: "https://okta.example.com",
    },
    {
      id: "p3",
      name: "ADFS",
      type: "saml",
      enabled: true,
      saml_idp_sso_url: "https://adfs.example.com/sso",
    },
  ]);
  render(<AuthenticationProvidersSettings />);
  expect(await screen.findByText("Okta")).toBeInTheDocument();
  expect(screen.getByText("ldaps://ldap.example.com")).toBeInTheDocument();
  expect(screen.getByText("https://okta.example.com")).toBeInTheDocument();
  expect(screen.getByText("https://adfs.example.com/sso")).toBeInTheDocument();
  expect(screen.getByText("OIDC")).toBeInTheDocument();
  expect(screen.getByText("SAML")).toBeInTheDocument();
  expect(screen.getByText("off")).toBeInTheDocument();
  expect(screen.getAllByText("on")).toHaveLength(2);
});

test("an empty provider list shows the empty state", async () => {
  m(listProviders).mockResolvedValue([]);
  render(<AuthenticationProvidersSettings />);
  expect(
    await screen.findByText("No identity providers configured yet."),
  ).toBeInTheDocument();
});

test("creates an LDAP provider with every field filled", async () => {
  await openAddDialog();
  type(/Display name/, "AD");
  type(/Tenant ID/, "tenant-1");
  fireEvent.click(screen.getByLabelText(/Just-in-time provisioning/));
  type(/JIT default role/, "viewer");
  fireEvent.click(screen.getByLabelText(/^Enabled$/));
  type(/LDAP server URL/, "ldaps://ad.corp");
  type(/Bind DN/, "cn=svc");
  type(/Bind password/, "vault:secret/ad");
  type(/User search base/, "ou=users");
  type(/User search filter/, "(uid=%s)");
  type(/Group search base/, "ou=groups");
  type(/Group search filter/, "(member=%s)");
  type(/TLS CA bundle path/, "/etc/ca.pem");
  type(/Connection timeout/, "abc");
  fireEvent.click(screen.getByLabelText(/Enable SCIM inbound provisioning/));
  type(/SCIM bearer token/, "vault:scim");
  dialogSave();
  await waitFor(() =>
    expect(createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "AD",
        type: "ldap",
        enabled: false,
        tenant_id: "tenant-1",
        jit_provisioning: true,
        jit_default_role: "viewer",
        ldap_server_url: "ldaps://ad.corp",
        ldap_bind_dn: "cn=svc",
        ldap_bind_password_secret_id: "vault:secret/ad",
        ldap_user_search_base: "ou=users",
        ldap_user_search_filter: "(uid=%s)",
        ldap_group_search_base: "ou=groups",
        ldap_group_search_filter: "(member=%s)",
        ldap_tls_ca_bundle_path: "/etc/ca.pem",
        ldap_connection_timeout: 10,
        scim_enabled: true,
        scim_bearer_token_secret_id: "vault:scim",
      }),
    ),
  );
  // Successful save closes the dialog and reloads.
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(listProviders).toHaveBeenCalledTimes(2);
});

test("creates an OIDC provider and sends a blank tenant as null", async () => {
  const dialog = await openAddDialog();
  type(/Display name/, "Okta");
  await chooseType(dialog, "OIDC");
  type(/OIDC issuer URL/, "https://okta");
  type(/Client ID/, "cid");
  type(/Client secret/, "vault:okta");
  type(/Redirect URI/, "https://sm/cb");
  type(/Scopes/, "openid email");
  type(/Discovery URL override/, "https://okta/.well-known");
  type(/Group claim name/, "roles");
  fireEvent.click(screen.getByLabelText(/Require multi-factor sign-in/));
  type(/Accepted assurance levels/, "mfa");
  dialogSave();
  await waitFor(() =>
    expect(createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "oidc",
        tenant_id: null,
        oidc_issuer_url: "https://okta",
        oidc_client_id: "cid",
        oidc_client_secret_secret_id: "vault:okta",
        oidc_redirect_uri: "https://sm/cb",
        oidc_scopes: "openid email",
        oidc_discovery_url: "https://okta/.well-known",
        oidc_group_claim: "roles",
        require_mfa: true,
        oidc_acr_values: "mfa",
      }),
    ),
  );
});

test("creates a SAML provider", async () => {
  const dialog = await openAddDialog();
  type(/Display name/, "ADFS");
  await chooseType(dialog, "SAML 2.0");
  type(/IdP Entity ID/, "urn:idp");
  type(/IdP SSO URL/, "https://idp/sso");
  type(/IdP signing certificate/, "PEM");
  type(/SP Entity ID/, "urn:sp");
  type(/SP ACS URL/, "https://sm/acs");
  type(/SP private key/, "vault:key");
  type(/Email attribute/, "mail");
  type(/Group attribute/, "memberOf");
  fireEvent.click(screen.getByLabelText(/Require signed assertions/));
  // No metadata URL until the provider exists.
  expect(screen.queryByLabelText(/SP metadata URL/)).toBeNull();
  dialogSave();
  await waitFor(() =>
    expect(createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "saml",
        saml_idp_entity_id: "urn:idp",
        saml_idp_sso_url: "https://idp/sso",
        saml_idp_x509_cert: "PEM",
        saml_sp_entity_id: "urn:sp",
        saml_sp_acs_url: "https://sm/acs",
        saml_sp_private_key_secret_id: "vault:key",
        saml_email_attribute: "mail",
        saml_group_attribute: "memberOf",
        saml_want_assertions_signed: false,
      }),
    ),
  );
});

test("editing a SAML provider shows its metadata URL and updates it", async () => {
  m(listProviders).mockResolvedValue([
    {
      id: "p3",
      name: "ADFS",
      type: "saml",
      enabled: true,
      tenant_id: "t9",
      jit_provisioning: true,
      jit_default_role: "admin",
      saml_idp_sso_url: "https://adfs/sso",
    },
  ]);
  m(updateProvider).mockResolvedValue({});
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("ADFS");
  fireEvent.click(screen.getByTitle("Edit"));
  expect(await screen.findByText("Edit Provider")).toBeInTheDocument();
  expect(screen.getByLabelText(/SP metadata URL/)).toHaveValue(
    `${globalThis.location.origin}/api/auth/saml/p3/metadata`,
  );
  expect(screen.getByLabelText(/Tenant ID/)).toHaveValue("t9");
  expect(screen.getByLabelText(/JIT default role/)).toHaveValue("admin");
  dialogSave();
  await waitFor(() =>
    expect(updateProvider).toHaveBeenCalledWith(
      "p3",
      expect.objectContaining({ name: "ADFS", tenant_id: "t9" }),
    ),
  );
  expect(createProvider).not.toHaveBeenCalled();
});

test("editing an LDAP provider fills defaults for missing fields", async () => {
  m(listProviders).mockResolvedValue([
    {
      ...provider,
      tenant_id: null,
      ldap_bind_dn: null,
      ldap_connection_timeout: null,
      oidc_scopes: null,
      oidc_group_claim: null,
    },
  ]);
  m(updateProvider).mockResolvedValue({});
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");
  fireEvent.click(screen.getByTitle("Edit"));
  await screen.findByText("Edit Provider");
  expect(screen.getByLabelText(/LDAP server URL/)).toHaveValue(
    "ldaps://ldap.example.com",
  );
  expect(screen.getByLabelText(/Connection timeout/)).toHaveValue(10);
  type(/Connection timeout/, "30");
  dialogSave();
  await waitFor(() =>
    expect(updateProvider).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({
        tenant_id: null,
        ldap_bind_dn: undefined,
        ldap_connection_timeout: 30,
        oidc_scopes: "openid profile email",
        oidc_group_claim: "groups",
        jit_default_role: "member",
      }),
    ),
  );
});

test("a provider save failure keeps the dialog open with an error", async () => {
  m(createProvider).mockRejectedValue(new Error("bad"));
  await openAddDialog();
  type(/Display name/, "Broken");
  dialogSave();
  expect(
    await screen.findByText("Could not save provider -- check the form."),
  ).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("delete is skipped when not confirmed and reports failures", async () => {
  const confirmSpy = vi.spyOn(globalThis, "confirm").mockReturnValue(false);
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");
  fireEvent.click(screen.getByTitle("Delete"));
  expect(deleteProvider).not.toHaveBeenCalled();

  confirmSpy.mockReturnValue(true);
  m(deleteProvider).mockRejectedValue(new Error("nope"));
  fireEvent.click(screen.getByTitle("Delete"));
  expect(
    await screen.findByText("Could not delete provider."),
  ).toBeInTheDocument();
  confirmSpy.mockRestore();
});

test("edits cross-provider settings before saving", async () => {
  m(updateIdpSettings).mockImplementation(async (s: unknown) => s);
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");
  fireEvent.click(screen.getByLabelText(/Allow local-password fallback/));
  type(/Max failed external attempts/, "9");
  fireEvent.click(screen.getAllByRole("button", { name: /^Save$/ })[0]);
  await waitFor(() =>
    expect(updateIdpSettings).toHaveBeenCalledWith({
      local_account_fallback: false,
      max_failed_attempts: 9,
    }),
  );
  // A non-numeric entry falls back to the default of 5.
  type(/Max failed external attempts/, "x");
  expect(screen.getByLabelText(/Max failed external attempts/)).toHaveValue(5);
});

test("a settings save failure is reported", async () => {
  m(updateIdpSettings).mockRejectedValue(new Error("x"));
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");
  fireEvent.click(screen.getAllByRole("button", { name: /^Save$/ })[0]);
  expect(
    await screen.findByText("Could not save settings."),
  ).toBeInTheDocument();
});

test("role mappings can be listed, added and removed", async () => {
  const mapping = {
    id: "rm1",
    external_group: "admins",
    role_name: "Admin",
    default_for_unmapped: true,
  };
  m(listRoleMappings).mockResolvedValue([mapping]);
  m(createRoleMapping).mockResolvedValue({});
  m(deleteRoleMapping).mockResolvedValue(undefined);
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");
  fireEvent.click(screen.getByTitle("Role mappings"));
  const dialog = await screen.findByRole("dialog");
  expect(await within(dialog).findByText("admins")).toBeInTheDocument();
  expect(within(dialog).getByText("✓")).toBeInTheDocument();

  // Blank inputs are ignored.
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  expect(createRoleMapping).not.toHaveBeenCalled();

  type(/^External group/, "  ops  ");
  type(/sysmanage role name/, " Operator ");
  fireEvent.click(within(dialog).getByLabelText("Default"));
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  await waitFor(() =>
    expect(createRoleMapping).toHaveBeenCalledWith("p1", {
      external_group: "ops",
      role_name: "Operator",
      default_for_unmapped: true,
    }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText(/^External group/)).toHaveValue(""),
  );

  const row = within(dialog).getByText("admins").closest("tr") as HTMLElement;
  fireEvent.click(within(row).getByRole("button"));
  await waitFor(() =>
    expect(deleteRoleMapping).toHaveBeenCalledWith("p1", "rm1"),
  );
  expect(listRoleMappings).toHaveBeenCalledTimes(3);

  fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("role mapping failures surface errors and a failed list is empty", async () => {
  m(listRoleMappings).mockRejectedValueOnce(new Error("x"));
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");
  fireEvent.click(screen.getByTitle("Role mappings"));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByText("No mappings yet.")).toBeInTheDocument();

  m(createRoleMapping).mockRejectedValue(new Error("x"));
  type(/^External group/, "ops");
  type(/sysmanage role name/, "Operator");
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  expect(await screen.findByText("Could not add mapping.")).toBeInTheDocument();
});

test("a role mapping delete failure is reported", async () => {
  m(listRoleMappings).mockResolvedValue([
    {
      id: "rm1",
      external_group: "admins",
      role_name: "Admin",
      default_for_unmapped: false,
    },
  ]);
  m(deleteRoleMapping).mockRejectedValue(new Error("x"));
  render(<AuthenticationProvidersSettings />);
  await screen.findByText("Corp LDAP");
  fireEvent.click(screen.getByTitle("Role mappings"));
  const dialog = await screen.findByRole("dialog");
  const row = (await within(dialog).findByText("admins")).closest(
    "tr",
  ) as HTMLElement;
  fireEvent.click(within(row).getByRole("button"));
  expect(
    await screen.findByText("Could not delete mapping."),
  ).toBeInTheDocument();
});

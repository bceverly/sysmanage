// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * External Identity Provider API client (Phase 10.5).
 *
 * Wraps ``/api/v1/idp-providers/*``, ``/api/v1/settings/idp``, and the two
 * anonymous OIDC endpoints used by the login redirect dance.
 */

import axiosInstance from './api';

export interface IdpProvider {
  id: string;
  name: string;
  type: 'ldap' | 'oidc' | 'saml';
  enabled: boolean;
  // Phase 13.1.E — per-tenant IdP + JIT. tenant_id null = server-global provider.
  tenant_id?: string | null;
  jit_provisioning?: boolean;
  jit_default_role?: string;
  ldap_server_url?: string | null;
  ldap_bind_dn?: string | null;
  ldap_bind_password_secret_id?: string | null;
  ldap_user_search_base?: string | null;
  ldap_user_search_filter?: string | null;
  ldap_group_search_base?: string | null;
  ldap_group_search_filter?: string | null;
  ldap_tls_ca_bundle_path?: string | null;
  ldap_connection_timeout?: number;
  oidc_issuer_url?: string | null;
  oidc_client_id?: string | null;
  oidc_client_secret_secret_id?: string | null;
  oidc_redirect_uri?: string | null;
  oidc_scopes?: string;
  oidc_discovery_url?: string | null;
  oidc_group_claim?: string;
  // Phase 13.1.E — SAML 2.0.
  saml_idp_entity_id?: string | null;
  saml_idp_sso_url?: string | null;
  saml_idp_x509_cert?: string | null;
  saml_sp_entity_id?: string | null;
  saml_sp_acs_url?: string | null;
  saml_sp_x509_cert?: string | null;
  saml_sp_private_key_secret_id?: string | null;
  saml_email_attribute?: string | null;
  saml_group_attribute?: string;
  saml_want_assertions_signed?: boolean;
  // Phase 13.1.E — SCIM 2.0 inbound provisioning.
  scim_enabled?: boolean;
  scim_bearer_token_secret_id?: string | null;
}

export interface IdpProviderCreate {
  name: string;
  type: 'ldap' | 'oidc' | 'saml';
  enabled?: boolean;
  // Phase 13.1.E — per-tenant IdP + JIT.
  tenant_id?: string | null;
  jit_provisioning?: boolean;
  jit_default_role?: string;
  ldap_server_url?: string;
  ldap_bind_dn?: string;
  ldap_bind_password_secret_id?: string;
  ldap_user_search_base?: string;
  ldap_user_search_filter?: string;
  ldap_group_search_base?: string;
  ldap_group_search_filter?: string;
  ldap_tls_ca_bundle_path?: string;
  ldap_connection_timeout?: number;
  oidc_issuer_url?: string;
  oidc_client_id?: string;
  oidc_client_secret_secret_id?: string;
  oidc_redirect_uri?: string;
  oidc_scopes?: string;
  oidc_discovery_url?: string;
  oidc_group_claim?: string;
  // Phase 13.1.E — SAML 2.0.
  saml_idp_entity_id?: string;
  saml_idp_sso_url?: string;
  saml_idp_x509_cert?: string;
  saml_sp_entity_id?: string;
  saml_sp_acs_url?: string;
  saml_sp_x509_cert?: string;
  saml_sp_private_key_secret_id?: string;
  saml_email_attribute?: string;
  saml_group_attribute?: string;
  saml_want_assertions_signed?: boolean;
  // Phase 13.1.E — SCIM 2.0 inbound provisioning.
  scim_enabled?: boolean;
  scim_bearer_token_secret_id?: string;
}

export interface IdpRoleMapping {
  id: string;
  provider_id: string;
  external_group: string;
  role_name: string;
  default_for_unmapped: boolean;
}

export interface IdpSettings {
  local_account_fallback: boolean;
  max_failed_attempts: number;
  updated_at?: string | null;
}

export const listProviders = async (): Promise<IdpProvider[]> => {
  const r = await axiosInstance.get<IdpProvider[]>('/api/v1/idp-providers');
  return r.data;
};

export const createProvider = async (
  payload: IdpProviderCreate,
): Promise<IdpProvider> => {
  const r = await axiosInstance.post<IdpProvider>('/api/v1/idp-providers', payload);
  return r.data;
};

export const updateProvider = async (
  id: string,
  patch: Partial<IdpProviderCreate>,
): Promise<IdpProvider> => {
  const r = await axiosInstance.put<IdpProvider>(
    `/api/v1/idp-providers/${id}`,
    patch,
  );
  return r.data;
};

export const deleteProvider = async (id: string): Promise<void> => {
  await axiosInstance.delete(`/api/v1/idp-providers/${id}`);
};

export const listRoleMappings = async (
  providerId: string,
): Promise<IdpRoleMapping[]> => {
  const r = await axiosInstance.get<IdpRoleMapping[]>(
    `/api/v1/idp-providers/${providerId}/role-mappings`,
  );
  return r.data;
};

export const createRoleMapping = async (
  providerId: string,
  payload: { external_group: string; role_name: string; default_for_unmapped?: boolean },
): Promise<IdpRoleMapping> => {
  const r = await axiosInstance.post<IdpRoleMapping>(
    `/api/v1/idp-providers/${providerId}/role-mappings`,
    payload,
  );
  return r.data;
};

export const deleteRoleMapping = async (
  providerId: string,
  mappingId: string,
): Promise<void> => {
  await axiosInstance.delete(
    `/api/v1/idp-providers/${providerId}/role-mappings/${mappingId}`,
  );
};

export const getIdpSettings = async (): Promise<IdpSettings> => {
  const r = await axiosInstance.get<IdpSettings>('/api/v1/settings/idp');
  return r.data;
};

export const updateIdpSettings = async (
  patch: Partial<IdpSettings>,
): Promise<IdpSettings> => {
  const r = await axiosInstance.put<IdpSettings>('/api/v1/settings/idp', patch);
  return r.data;
};

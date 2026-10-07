// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Phase 22.8: require multi-factor sign-in at the identity provider.  SSO
// leaves MFA to the IdP; with this on, a sign-in whose token does not say the
// user used more than one factor is refused.  OIDC and SAML only (an LDAP bind
// has no such statement).

import React from 'react';
import { FormControlLabel, Switch, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { IdpProviderCreate } from '../Services/externalIdp';

interface Props {
  draft: IdpProviderCreate;
  setDraft: (draft: IdpProviderCreate) => void;
}

const IdpMfaFields: React.FC<Props> = ({ draft, setDraft }) => {
  const { t } = useTranslation();
  if (draft.type !== 'oidc' && draft.type !== 'saml') return null;
  return (
    <>
      <FormControlLabel
        control={
          <Switch
            checked={!!draft.require_mfa}
            onChange={(e) => setDraft({ ...draft, require_mfa: e.target.checked })}
          />
        }
        label={t('idp.field.requireMfa', 'Require multi-factor sign-in')}
      />
      {draft.require_mfa && draft.type === 'oidc' && (
        <TextField
          label={t('idp.field.oidcAcrValues', 'Accepted assurance levels (acr)')}
          helperText={t(
            'idp.field.oidcAcrValuesHelp',
            'Optional: acr values that also count as multi-factor, separated by spaces; they are requested at sign-in. Otherwise the token must say amr includes mfa.',
          )}
          value={draft.oidc_acr_values ?? ''}
          onChange={(e) => setDraft({ ...draft, oidc_acr_values: e.target.value })}
          fullWidth
        />
      )}
      {draft.require_mfa && draft.type === 'saml' && (
        <TextField
          label={t('idp.field.samlMfaContexts', 'Multi-factor authentication contexts')}
          helperText={t(
            'idp.field.samlMfaContextsHelp',
            'AuthnContextClassRef values that count as multi-factor, one per line. Empty means Microsoft Entra ID\'s http://schemas.microsoft.com/claims/multipleauthn.',
          )}
          value={draft.saml_mfa_authn_contexts ?? ''}
          onChange={(e) => setDraft({ ...draft, saml_mfa_authn_contexts: e.target.value })}
          multiline
          minRows={2}
          fullWidth
        />
      )}
    </>
  );
};

export default IdpMfaFields;

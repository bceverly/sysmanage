#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Update vault configuration in /etc/sysmanage.yaml with production settings

SECURITY NOTE: This script requires environment variables to be set:
- VAULT_TOKEN: HashiCorp Vault service token

The unseal key is never written to the config: OpenBAO is unsealed from its
own root-only key file (/var/lib/openbao/init.json), because a copy of the
config would otherwise carry the key (ROADMAP 25.9).  Any unseal key an older
version wrote there is removed.

Example usage:
    export VAULT_TOKEN="s.your-vault-token-here"
    python update_vault_config.py
"""
import os
import sys

import yaml


def main():
    config_path = "/etc/sysmanage.yaml"

    if not os.path.exists(config_path):
        print(f"Error: Config file {config_path} not found")
        sys.exit(1)

    # Check for required environment variables
    vault_token = os.environ.get('VAULT_TOKEN')

    if not vault_token:
        print("Error: VAULT_TOKEN environment variable is required")
        sys.exit(1)

    # Read current config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Update vault configuration
    if 'vault' not in config:
        config['vault'] = {}

    config['vault'].update({
        'enabled': True,
        'url': 'http://localhost:8200',
        'token': vault_token,  # Token from environment
        'mount_path': 'secret',
        'timeout': 30,
        'verify_ssl': False,
        'dev_mode': False,  # Production mode
        'server': {
            'enabled': True,
            'config_file': './openbao.hcl',
            'data_path': './data/openbao',
            'initialized': True
        }
    })

    # Write updated config
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, indent=2)

    print("Vault configuration updated successfully")

if __name__ == "__main__":
    main()
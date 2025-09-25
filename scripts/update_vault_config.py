#!/usr/bin/env python3
"""
Update vault configuration in /etc/sysmanage.yaml with production settings
"""
import os
import sys
import yaml

def main():
    config_path = "/etc/sysmanage.yaml"

    if not os.path.exists(config_path):
        print(f"Error: Config file {config_path} not found")
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
        'token': 's.HmIwsLQbQQNFfwrSvN2eTkr4',  # Production token
        'mount_path': 'secret',
        'timeout': 30,
        'verify_ssl': False,
        'dev_mode': False,  # Production mode
        'server': {
            'enabled': True,
            'config_file': './openbao.hcl',
            'data_path': './data/openbao',
            'unseal_keys': ['Co5NFRUTmt8A/IS6fvyW/P4VGCphPM/3IW1bdXQrqVA='],
            'initialized': True
        }
    })

    # Write updated config
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, indent=2)

    print("Vault configuration updated successfully")

if __name__ == "__main__":
    main()
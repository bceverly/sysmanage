#!/usr/bin/env python3
"""
Generate Artillery configuration from sysmanage.yaml
Uses the same config loading logic as the backend to ensure consistency
"""

import os
import sys

import yaml


def load_sysmanage_config():
    """Load SysManage configuration using the same logic as backend/config/config.py"""
    # Check for system config first, then fall back to development config
    if os.name == "nt":  # Windows
        config_path = r"C:\ProgramData\SysManage\sysmanage.yaml"
    else:  # Unix-like (Linux, macOS, BSD)
        config_path = "/etc/sysmanage.yaml"

    # Fallback to development config if system config doesn't exist
    if not os.path.exists(config_path) and os.path.exists("sysmanage-dev.yaml"):
        config_path = "sysmanage-dev.yaml"

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

            # Apply defaults just like the main config
            if "host" not in config["api"]:
                config["api"]["host"] = "localhost"
            if "port" not in config["api"]:
                config["api"]["port"] = 8443

            return config, config_path
    except Exception as e:
        print(f"Error loading config file: {e}")
        sys.exit(1)

def resolve_host_for_client(config_host):
    """Resolve host for client connections, same logic as start.sh generate_urls function"""
    if config_host == "0.0.0.0":
        # When bound to 0.0.0.0, prefer localhost for client connections
        return "localhost"
    else:
        # Use the configured host directly
        return config_host

def generate_artillery_config():
    """Generate artillery.yml with correct target URL from sysmanage.yaml"""
    config, config_path = load_sysmanage_config()

    # Get API host and port
    api_host = config["api"]["host"]
    api_port = config["api"]["port"]

    # Resolve host for client connections
    resolved_api_host = resolve_host_for_client(api_host)
    target_url = f"http://{resolved_api_host}:{api_port}"

    print(f"Loaded config from: {config_path}")
    print(f"API config: {api_host}:{api_port}")
    print(f"Target URL: {target_url}")

    # Artillery configuration template
    artillery_config = {
        'config': {
            'target': target_url,
            'phases': [
                {
                    'duration': 10,
                    'arrivalRate': 2,
                    'name': "Warm-up"
                },
                {
                    'duration': 30,
                    'arrivalRate': 5,
                    'name': "Normal load"
                },
                {
                    'duration': 20,
                    'arrivalRate': 10,
                    'name': "Peak load"
                }
            ],
            'processor': "./artillery-processor.js",
            'ensure': {
                'p95': 500,
                'p99': 1000,
                'maxErrorRate': 1,
                'minRPS': 8
            }
        },
        'scenarios': [
            {
                'name': "Health Check",
                'weight': 30,
                'flow': [
                    {
                        'get': {
                            'url': "/health",
                            'capture': [
                                {
                                    'json': "$.status",
                                    'as': "healthStatus"
                                }
                            ]
                        }
                    },
                    {'think': 1}
                ]
            },
            {
                'name': "API Authentication Flow",
                'weight': 40,
                'flow': [
                    {
                        'post': {
                            'url': "/auth/login",
                            'json': {
                                'username': "test_user",
                                'password': "test_password"
                            },
                            'expect': [
                                {'statusCode': [200, 401]}
                            ],
                            'capture': [
                                {
                                    'json': "$.access_token",
                                    'as': "authToken"
                                }
                            ]
                        }
                    },
                    {'think': 2}
                ]
            },
            {
                'name': "Host Management API",
                'weight': 20,
                'flow': [
                    {
                        'get': {
                            'url': "/api/hosts",
                            'headers': {
                                'Authorization': "Bearer {{ authToken }}"
                            },
                            'expect': [
                                {'statusCode': [200, 401]}
                            ]
                        }
                    },
                    {'think': 1}
                ]
            },
            {
                'name': "WebSocket Connection Test",
                'weight': 10,
                'flow': [
                    {
                        'get': {
                            'url': "/ws",
                            'expect': [
                                {'statusCode': [101, 400, 426]}
                            ]
                        }
                    },
                    {'think': 3}
                ]
            }
        ]
    }

    # Write the generated config
    output_file = "artillery.yml"
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(artillery_config, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {output_file} with target: {target_url}")
    return target_url

if __name__ == "__main__":
    generate_artillery_config()
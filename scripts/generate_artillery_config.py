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
    """Generate artillery.yml with correct target URL from sysmanage.yaml.

    Scenario design notes:
    - Health Check hits /api/health (the actual route registered by the server,
      see backend/startup/route_registration.py).
    - API Authentication Flow logs in via POST /login. Body keys are 'userid'
      (an EmailStr per backend.api.auth.UserLogin) and 'password'. Response is
      {"Authorization": "<token>"}. Credentials match scripts/e2e_test_user.py
      so 'make test-performance' can reuse the same provisioning helper.
    - Host Management API uses the captured Authorization value as the header.
      sign_jwt() returns a raw JWT string (e.g. "eyJ…"); the JWTBearer
      dependency on the server side strips the "Bearer " prefix, so the
      client must add it. We send `Authorization: Bearer {{ authToken }}`.
    - WebSocket Endpoint Reachability does an HTTP GET on /api/agent/connect.
      FastAPI's WebSocket-only route returns 404 to an HTTP GET (the route is
      registered for the WS protocol, not for HTTP), but we still want to
      verify the path is reachable through the routing layer. Accepted codes:
      101 (upgrade succeeded — unlikely without WS handshake), 400/426
      (protocol mismatch), 404 (HTTP method not allowed on a WS-only route).
    """
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

    # Test credentials must match scripts/e2e_test_user.py exactly. The Makefile
    # 'test-performance' target invokes that script to provision the user before
    # the load run and to delete it after.
    perf_test_userid = "e2e-test@sysmanage.org"
    perf_test_password = "E2ETestPassword123!"  # nosec B105

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
                            'url': "/api/health",
                            'expect': [
                                {'statusCode': 200}
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
                            'url': "/login",
                            'json': {
                                'userid': perf_test_userid,
                                'password': perf_test_password
                            },
                            'expect': [
                                {'statusCode': 200}
                            ],
                            'capture': [
                                {
                                    'json': "$.Authorization",
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
                    # Inline login so we can reuse the captured token in the
                    # next request — Artillery scopes captured variables to
                    # a single scenario flow, not across scenarios.
                    {
                        'post': {
                            'url': "/login",
                            'json': {
                                'userid': perf_test_userid,
                                'password': perf_test_password
                            },
                            'expect': [
                                {'statusCode': 200}
                            ],
                            'capture': [
                                {
                                    'json': "$.Authorization",
                                    'as': "authToken"
                                }
                            ]
                        }
                    },
                    {
                        'get': {
                            'url': "/api/hosts",
                            'headers': {
                                # sign_jwt() returns a raw JWT; add the
                                # "Bearer " prefix that JWTBearer expects.
                                'Authorization': "Bearer {{ authToken }}"
                            },
                            'expect': [
                                {'statusCode': 200}
                            ]
                        }
                    },
                    {'think': 1}
                ]
            },
            {
                'name': "WebSocket Endpoint Reachability",
                'weight': 10,
                'flow': [
                    {
                        'get': {
                            'url': "/api/agent/connect",
                            'expect': [
                                # GET on a WebSocket endpoint: 101 = upgrade
                                # accepted, 400/426 = protocol mismatch,
                                # 404 = FastAPI's WS-only route doesn't
                                # accept HTTP. All are "the path resolved",
                                # which is what we want to confirm.
                                {'statusCode': [101, 400, 404, 426]}
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
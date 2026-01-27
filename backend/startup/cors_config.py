"""
CORS configuration module for the SysManage server.

This module provides functions to generate and configure CORS origins including
dynamic hostname discovery, network interface detection, and domain variations.
"""

import os
import socket

from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.startup.cors")


def get_cors_origins(web_ui_port, backend_api_port):  # NOSONAR
    """Generate CORS origins including dynamic hostname discovery."""
    logger.info("=== CORS ORIGINS GENERATION START ===")
    logger.info("Web UI port: %s, Backend API port: %s", web_ui_port, backend_api_port)

    # Check if running in CI mode - skip slow hostname resolution
    ci_mode = os.getenv("SYSMANAGE_CI_MODE", "").lower() == "true"
    if ci_mode:
        logger.info("CI mode detected - using minimal CORS origins")
        return [
            f"http://localhost:{web_ui_port}",
            f"http://localhost:{backend_api_port}",
            f"http://127.0.0.1:{web_ui_port}",
            f"http://127.0.0.1:{backend_api_port}",
        ]

    cors_origins = []

    # Always add localhost for development
    localhost_origins = [
        f"http://localhost:{web_ui_port}",
        f"http://localhost:{backend_api_port}",
        f"http://127.0.0.1:{web_ui_port}",
        f"http://127.0.0.1:{backend_api_port}",
    ]
    logger.info("Adding localhost origins: %s", localhost_origins)
    cors_origins.extend(localhost_origins)

    # Get system hostname and add variations
    try:
        hostname = socket.gethostname()
        logger.info("System hostname: %s", hostname)
        if hostname and hostname != "localhost":
            hostname_origins = [
                f"http://{hostname}:{web_ui_port}",
                f"http://{hostname}:{backend_api_port}",
            ]
            logger.info("Adding hostname origins: %s", hostname_origins)
            cors_origins.extend(hostname_origins)

        # Add FQDN if different from hostname
        try:
            fqdn = socket.getfqdn()
            logger.info("System FQDN: %s", fqdn)
            if fqdn and fqdn != hostname and fqdn != "localhost":
                fqdn_origins = [
                    f"http://{fqdn}:{web_ui_port}",
                    f"http://{fqdn}:{backend_api_port}",
                ]
                logger.info("Adding FQDN origins: %s", fqdn_origins)
                cors_origins.extend(fqdn_origins)
        except Exception as e:  # nosec B110
            logger.warning("Failed to get FQDN: %s", e)

        # Add common domain variations
        hostname_variations = [
            f"{hostname}.local",
            f"{hostname}.lan",
            f"{hostname}.theeverlys.lan",
            f"{hostname}.theeverlys.com",
        ]
        logger.info("Testing hostname variations: %s", hostname_variations)

        for variation in hostname_variations:
            variation_origins = [
                f"http://{variation}:{web_ui_port}",
                f"http://{variation}:{backend_api_port}",
            ]
            logger.info(
                "Adding variation origins for %s: %s", variation, variation_origins
            )
            cors_origins.extend(variation_origins)
    except Exception as e:  # nosec B110
        logger.warning("Failed to process hostname variations: %s", e)

    # Get network interface IPs
    try:
        hostname_for_ip = socket.gethostname()
        logger.info("Getting IP for hostname: %s", hostname_for_ip)
        host_ip = socket.gethostbyname(hostname_for_ip)
        logger.info("Resolved host IP: %s", host_ip)
        if host_ip and host_ip != "127.0.0.1":
            ip_origins = [
                f"http://{host_ip}:{web_ui_port}",
                f"http://{host_ip}:{backend_api_port}",
            ]
            logger.info("Adding IP origins: %s", ip_origins)
            cors_origins.extend(ip_origins)
    except Exception as e:  # nosec B110
        logger.warning("Failed to get network interface IPs: %s", e)

    # Get all network interface IPs (skip in CI mode for faster startup)
    ci_mode = os.getenv("SYSMANAGE_CI_MODE", "").lower() in ("true", "1", "yes")
    if ci_mode:
        logger.info(
            "CI mode detected - skipping network interface discovery for faster startup"
        )
    else:
        try:
            import netifaces

            logger.info("Getting all network interface IPs using netifaces")
            for interface in netifaces.interfaces():
                try:
                    addresses = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addresses:
                        for addr_info in addresses[netifaces.AF_INET]:
                            ip = addr_info.get("addr")
                            if (
                                ip
                                and ip != "127.0.0.1"
                                and not ip.startswith("169.254")
                            ):
                                interface_origins = [
                                    f"http://{ip}:{web_ui_port}",
                                    f"http://{ip}:{backend_api_port}",
                                ]
                                logger.info(
                                    "Adding interface %s IP origins: %s",
                                    interface,
                                    interface_origins,
                                )
                                cors_origins.extend(interface_origins)
                except Exception as e:
                    logger.warning(
                        "Failed to get addresses for interface %s: %s", interface, e
                    )
        except ImportError:
            if not ci_mode:
                # Fallback method using socket - try to get local IP by connecting to a remote address
                logger.info("netifaces not available, using socket fallback method")
                try:
                    # Create a socket and connect to a remote address to get local IP
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                        # Connect to a public DNS server (doesn't actually send data)
                        s.connect(("8.8.8.8", 80))
                        local_ip = s.getsockname()[0]
                        logger.info("Detected local IP via socket method: %s", local_ip)
                        if local_ip and local_ip != "127.0.0.1":
                            fallback_origins = [
                                f"http://{local_ip}:{web_ui_port}",
                                f"http://{local_ip}:{backend_api_port}",
                            ]
                            logger.info(
                                "Adding fallback IP origins: %s", fallback_origins
                            )
                            cors_origins.extend(fallback_origins)
                except Exception as e:
                    logger.warning("Failed to get local IP via socket fallback: %s", e)
            else:
                logger.info("CI mode detected - skipping socket fallback method")
        except Exception as e:  # nosec B110
            logger.warning("Failed to get all network interface IPs: %s", e)

    logger.info("Total CORS origins before deduplication: %d", len(cors_origins))
    unique_origins = list(set(cors_origins))  # Remove duplicates
    logger.info("Total CORS origins after deduplication: %d", len(unique_origins))
    logger.info("Final CORS origins: %s", unique_origins)
    logger.info("=== CORS ORIGINS GENERATION COMPLETE ===")
    return unique_origins

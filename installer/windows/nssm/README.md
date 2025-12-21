# NSSM - Non-Sucking Service Manager

This directory contains NSSM (Non-Sucking Service Manager), used to install
SysManage as a Windows service.

## Version

- **Version:** 2.24
- **Source:** https://nssm.cc/
- **License:** Public Domain

## Why bundled?

NSSM is bundled in the repository rather than downloaded at build time because:
1. The nssm.cc website is occasionally unavailable (503 errors)
2. GitHub Actions runners may be blocked by the site
3. Ensures reproducible builds

## Updating NSSM

To update NSSM:
1. Download the latest version from https://nssm.cc/download
2. Extract `win64/nssm.exe` from the ZIP
3. Replace `nssm.exe` in this directory
4. Update this README with the new version number

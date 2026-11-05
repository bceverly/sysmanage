#!/bin/sh
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# post-deinstall for the FreeBSD server package; build_pkg_manifest.py puts
# it in +MANIFEST.

echo "SysManage Server removed."
echo "Configuration files preserved in /usr/local/etc/sysmanage/"
echo "Logs preserved in /var/log/sysmanage/"
echo ""
echo "To completely remove, also run:"
echo "  sysrc -x sysmanage_enable"
echo "  rm -rf /usr/local/etc/sysmanage"
echo "  rm -rf /var/log/sysmanage"
echo "  rm -rf /var/lib/sysmanage"
echo "  rm -rf /etc/sysmanage"
# The post-install named our nginx config in nginx.conf; with the file gone,
# nginx would refuse to start.
if [ -f /usr/local/etc/nginx/nginx.conf ]; then
    sed -i '' -e '/include \/usr\/local\/etc\/nginx\/sysmanage-nginx.conf;/d' /usr/local/etc/nginx/nginx.conf
fi

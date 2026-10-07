# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""sysmanage-canary: an outside watcher for a SysManage server (Phase 22.9).

Everything that alerts inside the server stops when the server, its database
or its network is what failed.  The canary is a separate program -- its own
process, service, user and configuration -- that checks the console, the
backend, the database, the network and whether agents are still reporting,
and emails when something stops working.  It shares nothing with the server
at runtime: no imports from it, the system Python, and only the standard
library plus PyYAML and the PostgreSQL driver.
"""

__version__ = "1.0.0"

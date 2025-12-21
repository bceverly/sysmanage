================================================================================
SYSMANAGE LICENSING & PRICING
================================================================================

COMPETITIVE ANALYSIS
================================================================================

| Competitor                    | Per-Server/Year | Notes                          |
|-------------------------------|-----------------|--------------------------------|
| Ubuntu Pro + Landscape        | $500            | Server only, Ubuntu only       |
| Ansible Tower                 | $100-$125/node  | Automation only, no inventory  |
| ManageEngine Endpoint Central | $795-$1,695/50  | Complex tiering                |
| Red Hat Satellite             | ~$300-$500      | RHEL only, bundled pricing     |

Sysmanage differentiators:
- Multi-platform: Linux, Windows, macOS, FreeBSD, OpenBSD, NetBSD
- Self-hosted: No cloud dependency, full data sovereignty
- Open-core: Community edition is genuinely useful, not crippled
- Child host awareness: Purpose-built for virtualized environments
- Single pane of glass: Inventory, patching, compliance, monitoring in one tool

================================================================================
PRICING TIERS
================================================================================

COMMUNITY EDITION (FREE)
--------------------------------------------------------------------------------
- Up to 10 parent hosts
- Unlimited child hosts on those parents
- Phase 2 features (Foundation):
  - Access Groups and Registration Keys
  - Scheduled Update Profiles
  - Package Compliance Profiles
  - Activity Audit Log
  - Broadcast Messaging
- Community support only (GitHub Issues)
- No SLA

PROFESSIONAL ($75/parent host/year)
--------------------------------------------------------------------------------
- Unlimited parent hosts
- Child hosts: $15/child host/year
- Includes 5 child hosts per parent at no extra charge
- Phases 2-6 features:
  - All Community features, plus:
  - CVE/USN Vulnerability Tracking
  - Security Compliance Reporting
  - Alerting System
  - Multi-Factor Authentication
  - Repository Mirroring
  - External Identity Providers
  - Reboot Scheduling
  - Script Library
  - Host Lifecycle Management
  - Custom Metrics and Graphs
  - Process Management
  - Livepatch Integration
  - AI Health Analysis
  - Additional Hypervisors
  - Infrastructure Deployment
  - Firewall Recommendations
  - Child Host Profiles
  - Enhanced Snap Management
- Email support (business hours)
- 48-hour response SLA

ENTERPRISE ($150/parent host/year)
--------------------------------------------------------------------------------
- Unlimited parent hosts
- Child hosts: $25/child host/year
- Includes 10 child hosts per parent at no extra charge
- All features including Phase 7:
  - All Professional features, plus:
  - API Completeness (versioning, rate limiting, API keys)
  - Multi-Tenancy (isolated accounts/organizations)
  - GPG Key Management
  - Administrator Invitations
  - Platform-Native Logging
- 24/7 support option (+$50/host/year)
- 4-hour critical response SLA
- Priority feature requests
- Dedicated account manager (500+ hosts)

================================================================================
VOLUME DISCOUNTS
================================================================================

| Parent Host Count | Professional    | Enterprise      |
|-------------------|-----------------|-----------------|
| 1-25              | $75/host        | $150/host       |
| 26-100            | $60/host (20%)  | $120/host (20%) |
| 101-250           | $50/host (33%)  | $100/host (33%) |
| 251-500           | $40/host (47%)  | $85/host (43%)  |
| 500+              | Custom pricing  | Custom pricing  |

Multi-year discounts:
- 2-year commitment: Additional 10% off
- 3-year commitment: Additional 15% off

================================================================================
OPTIONAL ADD-ONS
================================================================================

| Add-on                              | Price/host/year |
|-------------------------------------|-----------------|
| CVE/Vulnerability Database Updates  | +$25            |
| AI Health Analysis (covers API)     | +$10            |
| Priority Support Upgrade            | +$50            |
| Custom Compliance Profiles          | +$30            |

Notes:
- CVE add-on provides real-time vulnerability feed updates beyond basic NVD
- AI Health Analysis covers third-party API costs (OpenAI, etc.)
- Priority Support available for Professional tier (included in Enterprise)
- Custom Compliance includes pre-built CIS Benchmarks and DISA STIG profiles

================================================================================
PRICING EXAMPLES
================================================================================

SMALL BUSINESS (10 servers, 20 VMs)
--------------------------------------------------------------------------------
Professional:
  10 parent hosts × $75                    = $750
  20 child hosts - 50 included (5×10)      = $0
  ------------------------------------------
  Total                                    = $750/year

Enterprise:
  10 parent hosts × $150                   = $1,500
  20 child hosts - 100 included (10×10)    = $0
  ------------------------------------------
  Total                                    = $1,500/year

Comparison: Ubuntu Pro would cost $5,000/year for servers alone

MEDIUM BUSINESS (50 servers, 100 VMs)
--------------------------------------------------------------------------------
Professional (26-100 tier = $60/host):
  50 parent hosts × $60                    = $3,000
  100 child hosts - 250 included (5×50)    = $0
  ------------------------------------------
  Total                                    = $3,000/year

Enterprise (26-100 tier = $120/host):
  50 parent hosts × $120                   = $6,000
  100 child hosts - 500 included (10×50)   = $0
  ------------------------------------------
  Total                                    = $6,000/year

Comparison: Ubuntu Pro would cost $25,000/year for servers alone

LARGE ORGANIZATION (200 servers, 500 VMs)
--------------------------------------------------------------------------------
Professional (101-250 tier = $50/host):
  200 parent hosts × $50                   = $10,000
  500 child hosts - 1000 included (5×200)  = $0
  ------------------------------------------
  Total                                    = $10,000/year

Enterprise (101-250 tier = $100/host):
  200 parent hosts × $100                  = $20,000
  500 child hosts - 2000 included (10×200) = $0
  ------------------------------------------
  Total                                    = $20,000/year

Comparison: Ubuntu Pro would cost $100,000/year for servers alone

ENTERPRISE (500 servers, 2000 VMs)
--------------------------------------------------------------------------------
Professional (251-500 tier = $40/host):
  500 parent hosts × $40                   = $20,000
  2000 child hosts - 2500 included (5×500) = $0
  ------------------------------------------
  Total                                    = $20,000/year

Enterprise (251-500 tier = $85/host):
  500 parent hosts × $85                   = $42,500
  2000 child hosts - 5000 included (10×500)= $0
  ------------------------------------------
  Total                                    = $42,500/year

With 3-year commitment (15% off):
  Professional: $17,000/year
  Enterprise: $36,125/year

Comparison: Ubuntu Pro would cost $250,000/year for servers alone

================================================================================
VALUE PROPOSITION SUMMARY
================================================================================

vs. Ubuntu Pro + Landscape ($500/server/year):
- 85% cheaper at Professional tier
- 70% cheaper at Enterprise tier
- Multi-platform support (not Ubuntu-only)
- Child hosts included (VMs don't multiply costs)

vs. Ansible Tower ($100-125/node/year):
- Similar pricing, vastly more features
- Ansible = automation only
- Sysmanage = inventory + patching + compliance + monitoring + automation

vs. ManageEngine Endpoint Central:
- Simpler pricing model
- Better multi-platform support
- Purpose-built for server management (not endpoint/desktop focused)

vs. Red Hat Satellite:
- Not locked to RHEL ecosystem
- Transparent pricing (no "contact sales")
- Supports mixed Linux distributions

================================================================================
IMPLEMENTATION NOTES
================================================================================

License Key Contents:
- Tier (Community/Professional/Enterprise)
- Parent host limit
- Child host limit
- Enabled feature codes
- Expiration date
- Customer identifier
- Cryptographic signature (ECDSA P-521)

See LICENSING-ARCHITECTURE.md for technical implementation details.

Grace Period Policy:
- 30-day grace period after license expiration
- During grace: Full functionality, warning banners
- After grace: Reverts to Community edition features
- Data is never deleted or locked

Upgrade/Downgrade Policy:
- Upgrades: Pro-rated credit applied immediately
- Downgrades: Take effect at renewal
- Tier changes: Can be made at any time via license portal

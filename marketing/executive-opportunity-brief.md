<!--
  SOURCE DOCUMENT — Markdown master for the SysManage Executive Overview.
  This file is written to convert cleanly to DOCX and PDF via
  scripts/build-marketing-brief.py. Conversion notes live in marketing/README.md.

  Layout conventions used below:
    - Screenshots / diagrams are marked with  [FIGURE: ...]  placeholders and a
      commented <img> pointing at images/<file>. Drop the asset in and uncomment.
    - Page breaks are marked with  <!-- PAGEBREAK -->  — the build script turns
      an exact PAGEBREAK marker into a real page break.
    - Callout/thesis boxes are marked with a leading  > **CALLOUT** —  blockquote
      so the build styles them as boxes.
    - Third-party trademark symbols are applied automatically at build time.
-->

<!-- COVER PAGE -->

<!-- [FIGURE: SysManage logo, ~2in wide, centered, generous whitespace above/below] -->

![SysManage](images/sysmanage-logo.svg)

# SysManage

## A Unified Control Plane for Heterogeneous Enterprise Infrastructure

**Executive Overview**

<!-- [FIGURE: use images/cover-dashboard.png as a full-bleed background faded ~15% behind the title block] -->
![](images/cover-dashboard.png)

*Confidential — prepared for discussion with prospective customers, design partners, strategic and channel partners, executive sales leadership, and investors.*

*© 2026 Bryan Everly. All rights reserved.*

<!-- PAGEBREAK -->

## Executive Summary

Enterprise infrastructure has become fundamentally more complex over the past decade. Windows, Linux, macOS, cloud workloads, virtualization, appliances, and increasingly specialized operating systems now coexist inside the same organization — and the number of tools required to manage them has grown right alongside them.

Existing management software evolved around individual operating systems rather than around heterogeneous infrastructure. Endpoint management, vulnerability management, compliance, automation, patching, and reporting are typically delivered by different vendors, each optimized for a single platform. The result is a fragmented, costly, and hard-to-secure operational environment: multiple consoles, multiple licenses, multiple integrations, and no single source of truth.

**SysManage was built to solve that problem.** It treats infrastructure as a unified fleet rather than a collection of separate operating systems — providing a single operational control plane that manages Linux, Windows, macOS, FreeBSD, OpenBSD, and NetBSD, and consolidates the operational, security, compliance, and lifecycle capabilities teams rely on, through one consistent experience.

The platform ships as an open-source Community Edition, with Professional, Enterprise, and Enterprise SaaS tiers that expand into AI-assisted operations, security, compliance, multi-tenancy, and air-gapped deployment.

The commercial opportunity has already been reviewed by an established European venture capital firm founded by experienced enterprise software executives. Their assessment of both the technical direction and the market need was positive; their primary recommendation was to strengthen the leadership team with an experienced enterprise software sales executive capable of accelerating commercial adoption. Both the product and its documentation have already been professionally translated into fourteen native languages, positioning the platform for global adoption from its earliest commercial stages.

> **CORE THESIS** — Infrastructure teams manage fleets, not operating systems. To the best of our knowledge, no commercially available enterprise platform offers comprehensive, first-class lifecycle management, patch management, compliance, vulnerability management, automation, and systems administration across Linux, Windows, macOS, FreeBSD, OpenBSD, and NetBSD through a single, unified control plane.

This document describes the market, why existing approaches fall short, why customers buy, the business opportunity and how it will be built, the founder behind it, the risks, and the relationships now being sought.

<!-- PAGEBREAK -->

## The Infrastructure Management Problem

Enterprise infrastructure has changed fundamentally over the past twenty years. Organizations once operated relatively uniform environments — Windows administrators managed Windows, UNIX administrators managed UNIX, and desktop and server management were separate disciplines. That distinction has disappeared.

A typical enterprise today may simultaneously operate:

- Windows desktops and servers
- Linux servers across multiple distributions
- macOS developer workstations
- Cloud-native and containerized workloads
- Virtualization and hypervisor infrastructure
- Network, storage, and security appliances
- FreeBSD, OpenBSD, and NetBSD systems
- Air-gapped environments and remote branch offices

Each platform often demands its own management tools, and organizations end up assembling an operational toolchain out of point products:

<!-- [FIGURE: "before" diagram — each OS wired to a different single-purpose tool, tangled. images/problem-fragmented.png] -->

| Operating system / function | Typical point product(s) |
|---|---|
| Windows | Microsoft Intune, Configuration Manager (MECM/SCCM) |
| macOS / Apple | Jamf |
| Red Hat Enterprise Linux | Red Hat Satellite |
| Ubuntu | Canonical Landscape |
| SUSE Linux Enterprise | SUSE Manager |
| FreeBSD / OpenBSD / NetBSD | Often custom scripts, or no commercial platform at all |
| Vulnerability management | Qualys, Rapid7, Tenable |
| Patch management | Automox, Action1, BigFix |
| Endpoint / cross-platform ops | Tanium, NinjaOne, ConnectWise, Datto RMM |
| Automation | Ansible and adjacent tooling |
| Compliance & reporting | Separate GRC / assessment tools |

Each of these solves part of the problem exceptionally well. None solves the operational challenge of managing heterogeneous infrastructure *as a unified environment*. Organizations spend significant time and money integrating products that were never designed to operate together — and infrastructure teams increasingly find themselves managing software rather than managing infrastructure.

<!-- PAGEBREAK -->

## Why Existing Solutions Fall Short

The systems management industry evolved around operating systems rather than around infrastructure. Most products were built by organizations whose business centered on a single platform, so support for competing operating systems is often limited, inconsistent, or entirely absent. This drives real operational cost:

**Fragmented visibility.** Critical operational information is scattered across multiple consoles. Administrators switch between products simply to understand the current state of a system.

**Operational complexity and cost.** Every product introduces another deployment model, another upgrade cycle, another security model, another API, and another licensing agreement. Instead of reducing operational complexity, the tooling often increases it.

**Inconsistent security.** Security teams struggle to produce consistent reporting when different operating systems are managed by different products. Compliance frameworks rarely distinguish between Windows and Linux. Attackers certainly do not — and operational visibility should not either.

**Uneven platform support.** FreeBSD, OpenBSD, and NetBSD remain widely deployed across networking, storage, telecommunications, hosting, research, and security environments, yet they receive little or no attention from mainstream enterprise management vendors. Organizations running these systems are forced to build custom tooling or accept reduced visibility.

This is not a criticism of the incumbents. Microsoft optimizes Windows. Jamf optimizes Apple. Red Hat optimizes RHEL. Canonical optimizes Ubuntu. Each is best-in-class within its domain. **Nobody optimizes all of them.** That gap is the opportunity.

<!-- PAGEBREAK -->

## The SysManage Vision — A Unified Control Plane

SysManage begins with a simple observation: infrastructure teams manage *fleets*, not operating systems. Every managed system shares the same core operational requirements regardless of the platform underneath it. Administrators need to know what is installed, whether it is vulnerable, whether it is compliant, whether it needs updating, what changed, who changed it, and whether it can be automated, secured, and reported on.

SysManage is designed around those questions rather than around operating-system boundaries. The objective is straightforward: **provide a unified operational control plane capable of managing heterogeneous infrastructure through a consistent user experience.**

<!-- [FIGURE: "after" diagram — six OSes (Linux, Windows, macOS, FreeBSD, OpenBSD, NetBSD) converging into one SysManage control plane. images/vision-unified.png] -->

We have deliberately retired the phrase "single pane of glass." It has become an industry cliché. "Unified control plane" better describes what SysManage actually is — the operational plane through which a heterogeneous fleet is administered, secured, and reported on as one environment.

## Why Now

Several long-term trends are converging to make this the right moment for a unified infrastructure management platform.

**Infrastructure diversity.** Enterprise infrastructure has become more heterogeneous, not less. The number of operating systems under management keeps rising.

**Cybersecurity as an operational discipline.** Inventory, patching, vulnerability management, and compliance are now foundational security controls, not merely operational functions. Operational and security tooling continue to converge.

**Vendor consolidation.** Enterprises are actively reducing the number of software vendors they manage — lowering licensing cost, simplifying procurement, and reducing training and integration overhead.

**Staffing constraints.** Infrastructure teams are expected to manage larger environments with fewer people. Automation and operational efficiency are no longer optional.

**Artificial intelligence.** AI lets administrators manage significantly larger environments by surfacing anomalies, recommending remediation, and generating automation — and it is most valuable when it operates against complete operational context rather than isolated point products. That advantage accrues directly to a unified control plane.

<!-- PAGEBREAK -->

## Market Opportunity

SysManage does not sit inside a single narrowly defined product category. It sits at the intersection of several of the largest and fastest-growing segments in enterprise software — endpoint management, IT operations, vulnerability management, patch management, compliance, and infrastructure automation, with managed services as an adjacent delivery channel.

![Enterprise software markets SysManage spans](images/market-chart.svg)

These categories overlap and should **not** be summed into a single total addressable market. Presented individually, they establish the scale of enterprise investment surrounding the operational disciplines SysManage unifies:

| Market segment | Representative size / forecast | Source |
|---|---|---|
| Enterprise Governance, Risk & Compliance (eGRC) | ~$134.9B by 2030 (13.2% CAGR) | Grand View Research |
| IT Operations Management | ~$64.9B by 2030 (12.3% CAGR) | Mordor Intelligence |
| IT Operations Analytics | ~$40.5B by 2032 | Fortune Business Insights |
| IT Service Management (ITSM) | ~$36.8B by 2032 (15.3% CAGR) | Fortune Business Insights |
| Security & Vulnerability Management | ~$24.1B by 2030 (6.5% CAGR) | MarketsandMarkets |
| Unified Endpoint Management (UEM) | ~$21.8B by 2030 (22.4% CAGR) | Grand View Research |
| Configuration Management & Infrastructure Automation | ~$12.2B by 2030 (~16% CAGR) | Virtue Market Research |
| Patch Management | ~$1.7B–$3B by 2032 (~10–14% CAGR) | Polaris / Research and Markets |
| Managed Services (adjacent channel) | ~$731B by 2030 (14.1% CAGR) | Grand View Research |

*Source URLs are listed in the References section. Figures should be refreshed against the latest published reports before external distribution, and overlapping segments should never be added together.*

The takeaway is not a single number — it is a position. SysManage addresses operational disciplines that collectively represent tens of billions of dollars in annual enterprise software spending, growing at double-digit rates.

**Serviceable market.** Initial commercialization focuses on organizations for which heterogeneous infrastructure is a genuine operational burden: Managed Service Providers (MSPs) and Managed Security Service Providers (MSSPs); enterprise IT organizations; cloud and hosting providers; and regulated verticals such as financial services, healthcare, government, higher education, and telecommunications. These organizations already buy many of the capabilities SysManage integrates — so the opportunity is less about creating new budget and more about consolidating existing operational spend.

<!-- PAGEBREAK -->

## Why Customers Buy

Organizations do not adopt infrastructure software for its features. They adopt it for outcomes — lower cost, lower risk, and higher productivity. Organizations buy SysManage because it can:

- **Reduce vendor count and licensing cost** — consolidate several single-OS tools into one platform.
- **Reduce operational complexity** — one interface, one deployment model, and one security model across the entire fleet.
- **Reduce administrator training and key-person risk** — teams learn one system instead of six.
- **Improve security posture** — consistent inventory, patching, and vulnerability visibility across every operating system.
- **Simplify compliance** — audit-ready reporting that spans the whole environment rather than stopping at OS boundaries.
- **Accelerate patching and remediation** — coordinated updates with a defensible audit trail.
- **Standardize operations** — the same processes and controls regardless of platform.

None of these is a technology feature. They are operational and financial outcomes — and they are what infrastructure and security leaders actually sign off on.

<!-- PAGEBREAK -->

## Competitive Landscape

The enterprise systems management market is mature, competitive, and populated by genuinely capable products. SysManage is not being built because those products are poor; in many cases they are best-in-class within their domain. The challenge is that nearly all of them were designed to optimize a specific operating system, deployment model, or operational discipline.

Microsoft has built an outstanding ecosystem around Windows. Jamf is synonymous with Apple. Red Hat Satellite and SUSE Manager focus on their respective Linux distributions, and Canonical Landscape on Ubuntu. Tanium, BigFix, NinjaOne, Automox, Action1, ConnectWise, Datto RMM, Qualys, Rapid7, and Tenable each address important portions of the operational lifecycle. Collectively, they illustrate the industry trend: organizations assemble an operational platform by integrating specialized products rather than adopting a unified operational architecture. As infrastructure grows more heterogeneous, that integration burden grows with it.

**Illustrative Positioning**

<!-- [FIGURE: capability x OS-support comparison matrix. images/competitive-matrix.png — SysManage row spans all six OSes as first-class; incumbents show concentrated coverage in their home OS] -->

| Capability | Windows-first suites | Apple (Jamf) | RHEL / Ubuntu / SUSE tools | Cross-platform RMM | **SysManage** |
|---|:---:|:---:|:---:|:---:|:---:|
| Windows | ● | ○ | ○ | ● | ● |
| Linux (multi-distro) | ◐ | ○ | ● (single vendor) | ◐ | ● |
| macOS | ◐ | ● | ○ | ◐ | ● |
| FreeBSD / OpenBSD / NetBSD | ○ | ○ | ○ | ○ | ● |
| Vulnerability management | ◐ | ○ | ◐ | ◐ | ● |
| Compliance & reporting | ◐ | ◐ | ◐ | ◐ | ● |
| Automation | ◐ | ◐ | ● | ● | ● |
| Multi-tenant (MSP) | ◐ | ◐ | ○ | ● | ● |
| Air-gapped deployment | ◐ | ○ | ◐ | ○ | ● |

*● first-class · ◐ partial / add-on · ○ limited or none. Illustrative positioning intended for discussion, not a certification; verify current vendor capabilities before external distribution.*

**Positioning.** SysManage is not trying to replace every specialized product. It seeks to become the operational control plane *around which* heterogeneous infrastructure is managed — consolidating where practical, integrating where specialized products add unique value. That mirrors how modern enterprises increasingly buy: prioritizing platforms that simplify operations across the whole environment over tools that merely excel within one operating system.

<!-- PAGEBREAK -->

## Why SysManage Is Different

> **THESIS** — To the best of our knowledge, no commercially available enterprise platform delivers comprehensive, first-class lifecycle management, compliance, vulnerability management, automation, inventory, reporting, and systems administration across Linux, Windows, macOS, FreeBSD, OpenBSD, and NetBSD through a single unified operational control plane.

SysManage was never designed as "Linux software with Windows support," nor as "Windows software with Linux support." It was designed from the beginning around heterogeneous infrastructure, with every supported operating system treated as a first-class citizen. That single architectural decision shapes the agent model, the data model, the user experience, and every capability built on top.

A small number of differentiators carry the story:

- **Unified control plane** across six operating systems, not one.
- **First-class BSD support** — a genuinely underserved segment in networking, storage, and security infrastructure.
- **Security-grade tenant isolation** suitable for MSPs and regulated environments.
- **Air-gapped deployment** for classified, critical-infrastructure, and disconnected environments.
- **Open-source core** that establishes adoption, transparency, and trust.
- **Built for a global market** — product and documentation already localized into fourteen languages.

<!-- PAGEBREAK -->

## Product Overview

SysManage brings the everyday work of infrastructure operations into one interface, applied consistently across every managed operating system. The screenshots below are drawn from the platform and from sysmanage.org.

![Unified fleet dashboard](images/product-dashboard.png)
**Unified fleet dashboard.** A single view of the entire estate — Windows, Linux, macOS, and BSD — with health, inventory, and status normalized into a consistent model. *Why it matters: one place to answer "what do we run, and what state is it in?"*

![Host detail — Windows](images/product-host-detail.png)
**Host detail.** Deep per-system inventory, installed software, and available updates, presented identically regardless of platform. *Why it matters: administrators learn one interface, not six.*

![Vulnerability & advisory management](images/product-vulnerabilities.png)
**Vulnerability & vendor-advisory management.** Consolidated visibility into exposure and vendor advisories across the fleet. *Why it matters: consistent risk posture across operating systems that would otherwise require separate scanners.*

![Compliance overview](images/product-compliance.png)
**Compliance assessment & reporting.** Assessments and exportable reports that treat the fleet as one environment. *Why it matters: audit-ready reporting that doesn't stop at the OS boundary.*

![Patch & update orchestration](images/product-patching.png)
**Patch & update orchestration.** Coordinated updates across platforms with visibility into what changed and who approved it. *Why it matters: faster remediation with a defensible audit trail.*

![Automation & scripts](images/product-automation.png)
**Automation.** Repeatable operational actions applied across heterogeneous systems. *Why it matters: manage larger fleets with fewer administrators.*

![Multi-site / multi-tenant view](images/product-tenancy.png)
**Multi-tenant administration.** Isolated per-customer or per-business-unit environments under one operational roof. *Why it matters: purpose-built for MSPs and distributed enterprises.*

![Reporting overview](images/product-reporting.png)
**Reporting.** Operational and executive-level reporting suitable for stakeholders beyond the operations team. *Why it matters: infrastructure posture communicated to leadership without manual assembly.*

<!-- PAGEBREAK -->

## Why the Architecture Matters

The technical design is covered in Appendix A. What matters commercially is that three architectural choices translate directly into market reach:

- **Enterprise SaaS & multi-tenancy** — each tenant is provisioned with its own isolated database, which unlocks the MSP channel and multi-business-unit enterprises.
- **Air-gapped deployment** — serves classified, critical-infrastructure, and disconnected environments that most competitors cannot address at all.
- **Tenant isolation & security model** — cryptographic separation suitable for regulated industries and government buyers.

Each of these is difficult to retrofit into a platform originally built around a single operating system, which is part of why the position is defensible.

## Commercialization Strategy

The plan deliberately sequences relationships before scale. SysManage follows a proven open-core model: a free Community Edition drives adoption and trust, while Professional, Enterprise, and Enterprise SaaS monetize the operational, security, and multi-tenant capabilities organizations depend on. (Edition detail is in Appendix B.)

- **Phase 1 — Design partners (current focus).** A small number of highly engaged organizations across different operational environments, to shape the roadmap and validate deployment models against real requirements.
- **Phase 2 — Enterprise customers.** Organizations operating heterogeneous infrastructure that value operational consolidation, security, and automation.
- **Phase 3 — Managed Service Providers.** MSPs and MSSPs, whose customer environments are heterogeneous by default; Enterprise SaaS was purpose-built for this operating model.
- **Phase 4 — Channel & technology partnerships.** Systems integrators, cybersecurity consultancies, and value-added resellers for reach and delivery; identity, SIEM, cloud, and DevOps integrations for stickiness.
- **Phase 5 — International expansion.** Fourteen-language localization is already in place, removing the usual barrier to markets beyond North America.

<!-- PAGEBREAK -->

## Market Validation

The commercial opportunity has already been reviewed by an established European venture capital firm founded by experienced enterprise software executives. Their assessment of both the technical direction and the market need was positive. Notably, their primary recommendation was **not** to change the product — it was to strengthen the commercial organization by adding experienced enterprise software sales leadership capable of accelerating adoption.

While the product continues to evolve, external feedback has consistently focused on commercial execution rather than technical direction. That is exactly the signal a founder wants at this stage: the hard, differentiated technology exists, and the remaining work is building the go-to-market organization around it.

> **Built for a global market from day one.** SysManage's user interface and documentation have already been professionally translated into fourteen native languages, enabling adoption by customers and partners well beyond North America without a future localization effort.

And the platform is real today — working software, an open-source Community Edition, and comprehensive documentation — not a concept awaiting a first build.

## Why SysManage Wins

Beyond the product itself, four structural reasons give this company a genuine chance to become a durable business:

1. **Founder–market fit.** The founder has spent three decades operating exactly this problem at enterprise scale — not encountering it for the first time (see Founder, next page).
2. **Market timing.** Infrastructure is getting more heterogeneous, security is becoming operational, teams are getting leaner, and AI is most valuable against unified data — every trend favors a unified control plane.
3. **Differentiated architecture.** First-class multi-OS support (including BSD), tenant isolation, and air-gapped deployment are hard to retrofit into single-OS incumbents. That is a moat, not a feature.
4. **Open-core adoption model.** A free Community Edition builds trust and a bottom-up adoption funnel, lowering customer-acquisition cost ahead of commercial conversion.

<!-- PAGEBREAK -->

## Founder

SysManage began with a problem the founder kept living, not a technology he set out to build.

At Cox Automotive, Bryan Everly was responsible for a large and remarkably heterogeneous infrastructure — Windows, multiple Linux distributions, macOS, and specialized systems spread across a sprawling estate. Answering a single operational question — what is installed, what is vulnerable, what changed, what is out of compliance — meant moving between separate consoles, each built for one operating system and blind to the others. The tools were individually capable and collectively incoherent. That same pattern repeated at organization after organization across three decades.

SysManage is the platform he wished existed every one of those times.

<!-- NO-TM-START -->

Bryan has spent more than three decades building, operating, and leading enterprise software and infrastructure organizations — including Canonical, Cummins, Aprimo, ExactTarget, Epsilon, Emerald Cloud Lab, and Cox Automotive — in roles spanning enterprise software, cloud infrastructure, systems management, and cybersecurity. In 2000 he founded PeopleStrategy, the enterprise human-resources SaaS company he built as an early bet on software-as-a-service years before it became the default model. He has participated in multiple public-company IPOs and has been involved on both the buy and sell sides of billion-dollar-plus mergers and acquisitions, and he holds a Master's degree in Information and Cybersecurity from the University of California, Berkeley.

<!-- NO-TM-END -->

The accomplishments matter less than what they add up to: SysManage was designed by someone who has operated heterogeneous enterprise infrastructure at scale, built and sold enterprise software, and understands what CIOs, operators, and investors actually care about — not someone who encountered the problem last year.

> *"After three decades running enterprise infrastructure, I finally built the platform I always wished existed — the tool I wanted every time I was handed a fleet and a drawer full of disconnected consoles to manage it with."*

<!-- PAGEBREAK -->

## Product Vision & Roadmap

The current platform establishes the operational foundation. Development over the next 18–24 months expands it along a few consistent axes:

- **AI-assisted operations** — anomaly identification, remediation recommendations, automation generation, and infrastructure-health summarization against the unified operational model.
- **Enterprise reporting** — executive dashboards and operational scorecards suitable for board-level and stakeholder reporting.
- **Integration breadth** — additional APIs and technology partnerships across identity, security, cloud, and DevOps ecosystems.
- **Deployment maturity** — continued growth of cloud-native and multi-tenant deployment while preserving customer-managed, on-premises, and air-gapped options.

Throughout that evolution, one principle holds: the objective is not simply to manage individual systems, but to provide a unified operational control plane for heterogeneous enterprise infrastructure.

## Risks & Mitigation

Building a company in a mature market carries real risks. Naming them — and how each is addressed — is part of how experienced operators build companies.

| Risk | Mitigation |
|---|---|
| **Commercial execution** — the product is strong; the company needs enterprise go-to-market leadership. | The single top priority is recruiting an experienced enterprise software sales executive; this is also exactly what the external VC review recommended. |
| **Brand recognition** — a new entrant against known incumbents. | Open-core adoption, first-class multi-OS and BSD support, and design-partner references build credibility bottom-up rather than through advertising spend. |
| **Large incumbents** could extend cross-platform support. | Their single-OS optimization and business-model gravity make first-class heterogeneous support hard to retrofit; the most underserved segments (BSD, air-gapped, true multi-OS) are structurally unattractive for them to prioritize. |
| **Talent & hiring** — building an enterprise go-to-market team is competitive. | A credible founder, a working product, and a clear market thesis are the strongest recruiting assets a young company can offer. |
| **Capital** — scaling go-to-market may require outside investment. | An open-core, low-burn model preserves optionality: the company can grow deliberately and raise on favorable terms rather than out of necessity. |

Naming these risks is deliberate. A clear-eyed view of what has to go right is a feature of a serious plan, not a weakness in it.

## Current Priorities — The Ask

At this stage the objective is not simply to acquire customers; it is to build the relationships needed to establish a durable enterprise software company. Current priorities:

- **Enterprise design partners** willing to influence the product roadmap.
- **Early enterprise customers** operating heterogeneous infrastructure.
- **Strategic technology alliances** across identity, security, cloud, and DevOps.
- **MSP and cybersecurity channel partnerships.**
- **Executive-level enterprise software sales leadership.**
- **Investors** experienced in enterprise infrastructure and cybersecurity.

If this vision resonates — or if someone in your network may find it compelling — an introduction and a brief initial conversation would be genuinely valuable.

## Closing

Enterprise infrastructure will continue to become more diverse, more distributed, and more security-sensitive. The software used to manage it has largely evolved in isolated silos. SysManage represents an opportunity to rethink enterprise systems management around the infrastructure itself rather than around individual operating systems.

The vision is straightforward: **one unified control plane for heterogeneous enterprise infrastructure.**

<!-- PAGEBREAK -->

## Appendix A — Reference Architecture

The architectural philosophy behind SysManage is intentionally straightforward.

![SysManage reference architecture](images/architecture.svg)

Each managed endpoint runs a lightweight native agent appropriate for its operating system. Agents communicate with the platform over mutually authenticated TLS. Operational data — inventory, software, vulnerabilities, compliance posture, configuration state, and administrative actions — is normalized into a consistent data model that is independent of the underlying operating system. Administrators interact with a single web interface whether the endpoint is Windows, Linux, macOS, FreeBSD, OpenBSD, or NetBSD.

Enterprise SaaS extends this architecture with strong tenant isolation. Rather than relying on shared tables keyed by a tenant identifier, each tenant is provisioned with its own PostgreSQL database. Short-lived database credentials are brokered through OpenBAO, minimizing long-lived secrets while keeping each tenant cryptographically and operationally isolated. The same architecture supports Enterprise SaaS, MSP delivery, regulated industries, government environments, customer-owned deployments, air-gapped installations, and hybrid cloud — scaling operationally while preserving separation and deployment flexibility.

![Multi-tenant isolation topology](images/multi-tenancy-topology.svg)

<!-- PAGEBREAK -->

## Appendix B — Product Editions

SysManage follows an open-core model. Pricing is intentionally omitted from this document; the table below describes what each edition is for and what it adds.

| Edition | For whom | What it adds |
|---|---|---|
| **Community** (open source) | Individuals, evaluators, and small teams | Core cross-platform management: inventory, updates, and unified administration across all six operating systems |
| **Professional** | Teams wanting AI-assisted operations | AI-assisted operational capabilities and enhanced monitoring |
| **Enterprise** | Larger and regulated organizations | Vulnerability and vendor-advisory management, compliance assessment and reporting, automation, identity integration, secrets management, firewall orchestration, audit/SIEM integration, multi-site federation, and enterprise support |
| **Enterprise SaaS** | MSPs and distributed enterprises | Hosted, multi-tenant architecture with per-tenant database isolation |

The full capability set spans operational, security, compliance, and lifecycle management; the editions above determine which capabilities are available and how the platform is operated and supported.

<!-- PAGEBREAK -->

## References

Market-sizing figures cited in this document are drawn from publicly accessible analyst and market-research summaries. They are presented individually and should not be summed into a single total addressable market. Refresh against the latest published reports before external distribution.

- Enterprise Governance, Risk & Compliance (eGRC) — Grand View Research: <https://www.grandviewresearch.com/industry-analysis/enterprise-governance-risk-compliance-egrc-market>
- IT Operations Management — Mordor Intelligence: <https://www.mordorintelligence.com/industry-reports/it-operations-management-market>
- IT Operations Analytics — Fortune Business Insights: <https://www.fortunebusinessinsights.com/it-operations-analytics-market-109837>
- IT Service Management (ITSM) — Fortune Business Insights: <https://www.fortunebusinessinsights.com/itsm-market-109485>
- Security & Vulnerability Management — MarketsandMarkets: <https://www.marketsandmarkets.com/Market-Reports/security-vulnerability-management-market-204180861.html>
- Unified Endpoint Management — Grand View Research: <https://www.grandviewresearch.com/industry-analysis/unified-endpoint-management-market>
- Unified Endpoint Management (2033 view) — Custom Market Insights: <https://www.custommarketinsights.com/report/unified-endpoint-management-market/>
- Configuration Management & Infrastructure Automation — Virtue Market Research: <https://virtuemarketresearch.com/report/configuration-management-infrastructure-automation-market>
- Patch Management — Polaris Market Research: <https://www.polarismarketresearch.com/industry-analysis/patch-management-market>
- Patch Management — Research and Markets: <https://www.researchandmarkets.com/report/patch-management>
- Managed Services — Grand View Research: <https://www.grandviewresearch.com/industry-analysis/managed-services-market>

<!-- PAGEBREAK -->

## Trademarks & Legal Notice

This document and its contents are confidential and proprietary. © 2026 Bryan Everly. All rights reserved. No part of this document may be reproduced or distributed without permission.

SysManage and the SysManage logo are trademarks of Bryan Everly.

All other product names, company names, brands, logos, service marks, and trademarks referenced in this document are the property of their respective owners and are used solely for identification and comparative-commentary purposes. Their use does not imply any affiliation with, endorsement by, or sponsorship by their respective owners.

Marks referenced in this document include, without limitation: Microsoft, Windows, Intune, and Configuration Manager (Microsoft Corporation); Apple and macOS (Apple Inc.); Jamf (Jamf Software, LLC); Red Hat, Red Hat Enterprise Linux, RHEL, Red Hat Satellite, and Ansible (Red Hat, Inc.); Ubuntu, Canonical, and Landscape (Canonical Ltd.); SUSE and SUSE Manager (SUSE LLC); Linux (Linus Torvalds); FreeBSD (The FreeBSD Foundation); NetBSD (The NetBSD Foundation); OpenBSD (Theo de Raadt and the OpenBSD project); PostgreSQL (The PostgreSQL Global Development Group); OpenBAO (a project of the Linux Foundation); Tanium (Tanium Inc.); BigFix (HCL Technologies Ltd.); NinjaOne (NinjaOne, LLC); ConnectWise (ConnectWise, LLC); Datto and Datto RMM (Datto, Inc.); Automox (Automox, Inc.); Action1 (Action1 Corporation); Qualys (Qualys, Inc.); Rapid7 (Rapid7, Inc.); Tenable (Tenable, Inc.); and Grand View Research, Fortune Business Insights, MarketsandMarkets, Mordor Intelligence, Virtue Market Research, Polaris Market Research, Research and Markets, and Custom Market Insights (their respective owners).

The ® and ™ symbols denote marks claimed by their respective owners. The absence of a symbol in any reference should not be construed as a waiver of any trademark or other intellectual-property rights.

*SysManage — https://sysmanage.org*

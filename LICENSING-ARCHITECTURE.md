================================================================================
SYSMANAGE LICENSING AND COMMERCIAL FEATURES ARCHITECTURE
================================================================================

This document describes the architecture for implementing commercial licensing
in sysmanage, including license key generation/validation, feature gating,
and the separation of community vs. paid code.

================================================================================
TABLE OF CONTENTS
================================================================================

1. Overview and Business Model
2. License Key Format and Cryptography
3. License Validation Flow
4. Feature Gating Architecture
5. Code Separation Strategy
6. Distribution and Installation
7. Implementation Details
8. Security Considerations

================================================================================
1. OVERVIEW AND BUSINESS MODEL
================================================================================

Tiers:
- Community Edition: Free, open source (AGPL), limited features
- Professional Edition: Paid, adds enterprise features
- Enterprise Edition: Paid, adds advanced features + support

License Types:
- Parent Host License: Physical/VM hosts running sysmanage-agent directly
- Child Host License: VMs/containers managed by a parent host (discounted)
- Unlimited: No host limits (enterprise tier)

Example Pricing Model:
- Community: Free, unlimited hosts, limited features
- Professional: $X/parent host/year + $Y/child host/year
- Enterprise: Custom pricing, unlimited hosts

================================================================================
2. LICENSE KEY FORMAT AND CRYPTOGRAPHY
================================================================================

License Key Structure:
----------------------
The license key is a signed JWT-like token that cannot be forged without
our private key. It contains all entitlement information.

Format: BASE64(HEADER).BASE64(PAYLOAD).BASE64(SIGNATURE)

Header (JSON):
{
  "alg": "ES512",        // ECDSA with P-521 curve (strongest)
  "typ": "SMLIC",        // SysManage License
  "ver": 1               // License format version
}

Payload (JSON):
{
  "lic": "uuid",                    // Unique license ID
  "cust": "customer-uuid",          // Customer ID
  "org": "Acme Corp",               // Organization name
  "email": "admin@acme.com",        // Contact email
  "tier": "professional",           // community|professional|enterprise
  "parent_hosts": 50,               // Max parent hosts (0 = unlimited)
  "child_hosts": 200,               // Max child hosts (0 = unlimited)
  "features": ["vuln", "compliance", "alerts", "mfa"],  // Enabled feature codes
  "iat": 1702400000,                // Issued at (Unix timestamp)
  "exp": 1733936000,                // Expires at (Unix timestamp)
  "grace": 604800,                  // Grace period in seconds (7 days)
  "offline_days": 30,               // Days allowed without phone-home
  "hw_lock": null                   // Optional: lock to specific server fingerprint
}

Signature:
- ECDSA P-521 signature over HEADER.PAYLOAD
- Only we have the private key; public key embedded in sysmanage server
- Cannot be forged or modified without invalidating signature

Why ECDSA P-521:
- Asymmetric: We sign with private key, validate with public key
- P-521 is strongest standard curve (521-bit key)
- Signatures are ~132 bytes (reasonable size)
- Quantum-resistant alternatives (Dilithium) could be added later

Key Generation (Our Side):
--------------------------
```python
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

# Generate once, store private key SECURELY
private_key = ec.generate_private_key(ec.SECP521R1(), default_backend())
public_key = private_key.public_key()

# Private key: NEVER in customer code, only in license generation server
# Public key: Embedded in sysmanage server code for validation
```

License Generation (Our License Server):
----------------------------------------
```python
import json
import base64
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

def generate_license(customer_data, private_key):
    header = {"alg": "ES512", "typ": "SMLIC", "ver": 1}

    payload = {
        "lic": str(uuid.uuid4()),
        "cust": customer_data["customer_id"],
        "org": customer_data["organization"],
        "email": customer_data["email"],
        "tier": customer_data["tier"],
        "parent_hosts": customer_data["parent_hosts"],
        "child_hosts": customer_data["child_hosts"],
        "features": customer_data["features"],
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(days=365)).timestamp()),
        "grace": 604800,
        "offline_days": 30,
        "hw_lock": customer_data.get("hw_lock")
    }

    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    message = f"{header_b64}.{payload_b64}".encode()
    signature = private_key.sign(message, ec.ECDSA(hashes.SHA512()))
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{header_b64}.{payload_b64}.{signature_b64}"
```

================================================================================
3. LICENSE VALIDATION FLOW
================================================================================

On Server Startup:
------------------
1. Load license key from database or config file
2. Validate signature using embedded public key
3. Check expiration (with grace period consideration)
4. Count current parent/child hosts against limits
5. Cache validated license in memory
6. Start background task for periodic re-validation

Validation Code (sysmanage Server):
-----------------------------------
```python
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_public_key

# Public key embedded in code (this is safe - it's public)
PUBLIC_KEY_PEM = """
-----BEGIN PUBLIC KEY-----
MIGbMBAGByqGSM49AgEGBSuBBAAjA4GGAAQBx...
-----END PUBLIC KEY-----
"""

class LicenseValidator:
    def __init__(self):
        self.public_key = load_pem_public_key(PUBLIC_KEY_PEM.encode())
        self.cached_license = None

    def validate(self, license_key: str) -> LicenseInfo:
        parts = license_key.split(".")
        if len(parts) != 3:
            raise InvalidLicenseError("Malformed license key")

        header_b64, payload_b64, signature_b64 = parts

        # Decode payload
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))

        # Verify signature
        message = f"{header_b64}.{payload_b64}".encode()
        signature = base64.urlsafe_b64decode(signature_b64 + "==")

        try:
            self.public_key.verify(signature, message, ec.ECDSA(hashes.SHA512()))
        except Exception:
            raise InvalidLicenseError("Invalid signature - license may be tampered")

        # Check expiration
        now = int(datetime.utcnow().timestamp())
        if now > payload["exp"] + payload.get("grace", 0):
            raise LicenseExpiredError("License has expired")

        return LicenseInfo(
            license_id=payload["lic"],
            tier=payload["tier"],
            parent_hosts=payload["parent_hosts"],
            child_hosts=payload["child_hosts"],
            features=set(payload["features"]),
            expires_at=datetime.fromtimestamp(payload["exp"]),
            is_expired=now > payload["exp"],
            in_grace_period=now > payload["exp"]
        )
```

Phone-Home Validation (Optional):
---------------------------------
For additional security, the server can periodically validate with our
license server:

```
POST https://license.sysmanage.io/v1/validate
{
  "license_id": "uuid",
  "server_fingerprint": "sha256-of-server-identity",
  "parent_host_count": 45,
  "child_host_count": 180
}

Response:
{
  "valid": true,
  "message": "License valid",
  "features_update": null,  // Or updated feature list
  "revoked": false
}
```

This allows:
- License revocation for chargebacks/violations
- Usage tracking for billing
- Feature flag updates without new license key
- Grace period for offline operation (offline_days in license)

================================================================================
4. FEATURE GATING ARCHITECTURE
================================================================================

Feature Registry:
-----------------
Each paid feature has a unique code that maps to functionality:

```python
class FeatureCode:
    # Phase 2 - Security (Professional+)
    VULNERABILITY_TRACKING = "vuln"
    COMPLIANCE_REPORTING = "compliance"
    ALERTING = "alerts"
    MFA = "mfa"

    # Phase 3 - Enterprise (Professional+)
    REPOSITORY_MIRRORING = "repo_mirror"
    EXTERNAL_IDP = "ext_idp"
    REBOOT_SCHEDULING = "reboot_sched"
    SCRIPT_LIBRARY = "scripts"

    # Phase 4 - Monitoring (Professional+)
    CUSTOM_METRICS = "metrics"
    PROCESS_MANAGEMENT = "proc_mgmt"
    LIVEPATCH = "livepatch"
    AI_HEALTH = "ai_health"

    # Enterprise Only
    MULTI_TENANCY = "multi_tenant"
    API_KEYS = "api_keys"

# Tier -> Default Features mapping
TIER_FEATURES = {
    "community": set(),  # No paid features
    "professional": {
        FeatureCode.VULNERABILITY_TRACKING,
        FeatureCode.COMPLIANCE_REPORTING,
        FeatureCode.ALERTING,
        FeatureCode.MFA,
        FeatureCode.REPOSITORY_MIRRORING,
        FeatureCode.EXTERNAL_IDP,
        FeatureCode.REBOOT_SCHEDULING,
        FeatureCode.SCRIPT_LIBRARY,
        FeatureCode.CUSTOM_METRICS,
        FeatureCode.PROCESS_MANAGEMENT,
        FeatureCode.LIVEPATCH,
        FeatureCode.AI_HEALTH,
    },
    "enterprise": {
        # All professional features plus:
        FeatureCode.MULTI_TENANCY,
        FeatureCode.API_KEYS,
        # ... all features
    }
}
```

Feature Check Decorator (Backend):
----------------------------------
```python
from functools import wraps
from fastapi import HTTPException

def requires_feature(feature_code: str):
    """Decorator to gate API endpoints by feature"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            license_info = get_current_license()
            if not license_info.has_feature(feature_code):
                raise HTTPException(
                    status_code=402,  # Payment Required
                    detail={
                        "error": "feature_not_licensed",
                        "feature": feature_code,
                        "message": f"This feature requires a Professional or Enterprise license",
                        "upgrade_url": "https://sysmanage.io/pricing"
                    }
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage:
@router.get("/api/vulnerabilities")
@requires_feature(FeatureCode.VULNERABILITY_TRACKING)
async def get_vulnerabilities():
    ...
```

Frontend Feature Gating:
------------------------
```typescript
// License context provided by API
interface LicenseInfo {
  tier: 'community' | 'professional' | 'enterprise';
  features: string[];
  parentHostsLimit: number;
  childHostsLimit: number;
  expiresAt: string;
  inGracePeriod: boolean;
}

// Hook for checking features
function useFeature(featureCode: string): boolean {
  const { license } = useLicenseContext();
  return license?.features.includes(featureCode) ?? false;
}

// Component usage
function VulnerabilityPage() {
  const hasVuln = useFeature('vuln');

  if (!hasVuln) {
    return <UpgradePrompt feature="Vulnerability Tracking" />;
  }

  return <VulnerabilityDashboard />;
}

// Or hide menu items entirely
function Navbar() {
  const hasVuln = useFeature('vuln');

  return (
    <nav>
      <NavItem to="/hosts">Hosts</NavItem>
      {hasVuln && <NavItem to="/vulnerabilities">Vulnerabilities</NavItem>}
      ...
    </nav>
  );
}
```

================================================================================
5. CODE SEPARATION STRATEGY
================================================================================

There are several approaches to separating community vs. paid code:

OPTION A: Single Repository with Feature Flags (Recommended)
------------------------------------------------------------
All code in one repo, paid features gated by license check at runtime.

Pros:
- Simplest to develop and maintain
- Single codebase, single deployment
- No code duplication
- Easier testing

Cons:
- Paid code visible in open source repo (but not usable without license)
- Determined attacker could patch out license checks

Mitigation:
- License checks at API layer (easy to audit)
- Obfuscate particularly sensitive algorithms
- Phone-home validation for enterprise features
- Legal protection (DMCA, license terms)

Structure:
```
sysmanage/
├── backend/
│   ├── api/
│   │   ├── vulnerabilities.py      # @requires_feature("vuln")
│   │   ├── compliance.py           # @requires_feature("compliance")
│   │   └── ...
│   ├── licensing/
│   │   ├── validator.py            # License validation
│   │   ├── feature_gate.py         # Feature decorators
│   │   └── public_key.py           # Embedded public key
│   └── ...
```

OPTION B: Separate Private Repository for Paid Features
-------------------------------------------------------
Core is open source, paid features in private repo as plugins.

Pros:
- Paid code not visible publicly
- Clear separation of concerns
- Can distribute paid code separately

Cons:
- More complex development workflow
- Plugin API must be stable
- Code duplication risk
- Harder to test integrated system

Structure:
```
sysmanage/              (public, GitHub)
├── backend/
│   ├── plugins/
│   │   ├── __init__.py
│   │   └── loader.py   # Plugin discovery and loading
│   └── ...

sysmanage-enterprise/   (private, separate repo)
├── plugins/
│   ├── vulnerability_tracking/
│   │   ├── __init__.py
│   │   ├── api.py
│   │   └── models.py
│   ├── compliance/
│   └── ...
└── setup.py            # Installable as sysmanage-enterprise package
```

Plugin Loader:
```python
# backend/plugins/loader.py
import importlib
import pkg_resources

def load_plugins():
    """Discover and load enterprise plugins if installed and licensed"""
    plugins = {}

    # Check for enterprise package
    try:
        import sysmanage_enterprise
        for plugin in sysmanage_enterprise.PLUGINS:
            if get_license().has_feature(plugin.feature_code):
                plugins[plugin.name] = plugin.load()
    except ImportError:
        pass  # Enterprise package not installed

    return plugins
```

OPTION C: Hybrid - Core Open, Sensitive Code Compiled
-----------------------------------------------------
Most code open source, but particularly valuable algorithms compiled
to binary Python extensions using Cython or PyArmor.

Pros:
- Protects most valuable IP
- Open source for community contributions
- Harder to reverse engineer

Cons:
- Compilation complexity
- Platform-specific binaries
- Still not impossible to reverse

Structure:
```
sysmanage/
├── backend/
│   ├── api/
│   │   └── vulnerabilities.py      # Open, calls compiled module
│   └── _enterprise/                # Compiled modules
│       ├── vuln_engine.cpython-311-x86_64-linux-gnu.so
│       └── compliance_engine.cpython-311-x86_64-linux-gnu.so
```

RECOMMENDATION: Start with Option A (single repo, feature flags)
----------------------------------------------------------------
- Simplest to implement and maintain
- License signature provides sufficient protection for most cases
- Add Option C (compiled modules) later for high-value algorithms
- Legal terms prohibit circumvention (similar to other commercial software)

================================================================================
6. DISTRIBUTION AND INSTALLATION
================================================================================

License Key Installation:
-------------------------
Users obtain license key from our website/portal after purchase.

Method 1: Web UI
```
Settings -> License -> Enter License Key -> [Paste key] -> Activate
```

Method 2: Config File
```yaml
# /etc/sysmanage.yaml
license:
  key: "eyJhbGciOiJFUzUxMi..."
```

Method 3: Environment Variable
```bash
export SYSMANAGE_LICENSE_KEY="eyJhbGciOiJFUzUxMi..."
```

Method 4: API
```bash
curl -X POST https://sysmanage.local/api/license \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"key": "eyJhbGciOiJFUzUxMi..."}'
```

Enterprise Plugin Distribution (if using Option B):
---------------------------------------------------

Option B1: Private PyPI
```bash
pip install sysmanage-enterprise \
  --index-url https://pypi.sysmanage.io/simple/ \
  --extra-index-url https://pypi.org/simple/
```
- Requires authentication (license key as password)
- Our private PyPI validates license before serving package

Option B2: Direct Download with License Validation
```bash
# Download script validates license first
curl -H "X-License-Key: $KEY" https://download.sysmanage.io/enterprise/latest.tar.gz
```

Option B3: Apt/Yum Repository
```bash
# Add repo with license key authentication
echo "deb https://$LICENSE_KEY:x@apt.sysmanage.io/enterprise stable main" \
  > /etc/apt/sources.list.d/sysmanage-enterprise.list
apt update && apt install sysmanage-enterprise
```

================================================================================
7. IMPLEMENTATION DETAILS
================================================================================

Database Schema:
----------------
```sql
-- License storage
CREATE TABLE license (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    license_key TEXT NOT NULL,
    license_id VARCHAR(36) NOT NULL,  -- From license payload
    tier VARCHAR(20) NOT NULL,
    organization VARCHAR(255),
    parent_hosts_limit INTEGER NOT NULL,
    child_hosts_limit INTEGER NOT NULL,
    features JSONB NOT NULL,
    issued_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    installed_at TIMESTAMP DEFAULT NOW(),
    last_validated_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,

    CONSTRAINT single_active_license UNIQUE (is_active)
        WHERE is_active = TRUE
);

-- License validation history
CREATE TABLE license_validation_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    license_id VARCHAR(36) NOT NULL,
    validated_at TIMESTAMP DEFAULT NOW(),
    validation_type VARCHAR(20),  -- 'local' or 'remote'
    parent_host_count INTEGER,
    child_host_count INTEGER,
    result VARCHAR(20),  -- 'valid', 'expired', 'over_limit', 'revoked'
    details JSONB
);
```

License Info API Endpoint:
--------------------------
```python
@router.get("/api/license")
async def get_license_info(current_user: str = Depends(get_current_user)):
    """Return current license information for UI"""
    license = get_current_license()

    # Count current usage
    parent_count = db.query(Host).filter(Host.is_parent == True).count()
    child_count = db.query(Host).filter(Host.is_parent == False).count()

    return {
        "tier": license.tier,
        "organization": license.organization,
        "features": list(license.features),
        "limits": {
            "parent_hosts": license.parent_hosts,
            "child_hosts": license.child_hosts
        },
        "usage": {
            "parent_hosts": parent_count,
            "child_hosts": child_count
        },
        "expires_at": license.expires_at.isoformat(),
        "in_grace_period": license.in_grace_period,
        "days_remaining": (license.expires_at - datetime.utcnow()).days
    }
```

Host Count Enforcement:
-----------------------
```python
@router.post("/api/agent/register")
async def register_agent(data: AgentRegistration):
    license = get_current_license()

    is_child = data.parent_host_id is not None

    if is_child:
        current = db.query(Host).filter(Host.parent_host_id.isnot(None)).count()
        if license.child_hosts > 0 and current >= license.child_hosts:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "child_host_limit_reached",
                    "limit": license.child_hosts,
                    "current": current,
                    "message": "Child host limit reached. Please upgrade your license."
                }
            )
    else:
        current = db.query(Host).filter(Host.parent_host_id.is_(None)).count()
        if license.parent_hosts > 0 and current >= license.parent_hosts:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "parent_host_limit_reached",
                    "limit": license.parent_hosts,
                    "current": current,
                    "message": "Parent host limit reached. Please upgrade your license."
                }
            )

    # Proceed with registration...
```

================================================================================
8. SECURITY CONSIDERATIONS
================================================================================

Threats and Mitigations:
------------------------

1. License Key Sharing
   - Threat: Customer shares key with others
   - Mitigation: Phone-home validation tracks usage, hardware locking option,
     terms of service prohibit sharing

2. License Key Forgery
   - Threat: Attacker creates fake license key
   - Mitigation: ECDSA P-521 signature - cannot forge without private key

3. License Check Bypass
   - Threat: Attacker patches code to skip license checks
   - Mitigation:
     - Multiple check points throughout code
     - Obfuscate critical paths
     - Phone-home for enterprise features
     - Legal terms (DMCA protection)
     - Compiled modules for sensitive algorithms

4. Replay/Reuse of Expired License
   - Threat: Use old license after expiration
   - Mitigation: Expiration in signed payload, clock checks, phone-home

5. Time Manipulation
   - Threat: Set system clock back to extend license
   - Mitigation: Phone-home validation, NTP checks, monotonic counters

6. Private Key Compromise
   - Threat: Our signing key is leaked
   - Mitigation:
     - HSM for key storage
     - Key rotation capability (version field in header)
     - Revocation list

Best Practices:
---------------
- Never log full license keys
- Store license key encrypted at rest in database
- Use constant-time comparison for signature validation
- Rate limit license validation API
- Monitor for suspicious patterns (many validations, geographic anomalies)
- Include license audit in security reviews

================================================================================
LICENSE GENERATION SERVICE (Our Infrastructure)
================================================================================

We need a separate service (not in sysmanage repo) for:
- Customer portal (purchase, manage licenses)
- License generation API
- Phone-home validation endpoint
- Usage analytics
- Revocation management

This would be hosted at license.sysmanage.io and is outside the scope
of the sysmanage codebase itself.

Tech Stack Suggestions:
- Simple FastAPI service
- PostgreSQL for customer/license data
- Stripe integration for payments
- Private key in HSM or AWS KMS
- Deployed on isolated infrastructure

================================================================================
MIGRATION PATH
================================================================================

Phase 1: Add license infrastructure (no enforcement)
- Add License model and validation code
- Add license management UI
- All features remain free

Phase 2: Soft enforcement (warnings only)
- Add feature gates that log warnings
- UI shows "upgrade" prompts but doesn't block
- Collect usage data

Phase 3: Full enforcement
- Feature gates return 402 errors
- Host limits enforced
- Grace period for existing users

================================================================================

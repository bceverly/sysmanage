#!/usr/bin/env python3
"""
Quick script to verify test model synchronization between conftest files.

Usage: python scripts/check_test_models.py
"""

import re
import sys
from pathlib import Path

def extract_models_from_main_conftest():
    """Extract model names from main conftest via Alembic imports."""
    models = set()
    models_file = Path("backend/persistence/models.py")

    if not models_file.exists():
        return models

    with open(models_file) as f:
        content = f.read()
        # Find class definitions
        class_pattern = r'^class\s+(\w+)\(.*Base.*\):$'
        for match in re.finditer(class_pattern, content, re.MULTILINE):
            models.add(match.group(1))

    return models

def extract_models_from_api_conftest():
    """Extract manually defined models from API conftest."""
    models = set()
    api_conftest = Path("tests/api/conftest.py")

    if not api_conftest.exists():
        return models

    with open(api_conftest) as f:
        content = f.read()
        # Find TestBase class definitions
        class_pattern = r'class\s+(\w+)\(TestBase\):'
        for match in re.finditer(class_pattern, content):
            models.add(match.group(1))

        # Also check monkey patching
        patch_pattern = r'models\.(\w+)\s*='
        for match in re.finditer(patch_pattern, content):
            models.add(match.group(1))

    return models

def main():
    """Check for model sync issues."""
    print("🔍 Checking test model synchronization...")

    main_models = extract_models_from_main_conftest()
    api_models = extract_models_from_api_conftest()

    print(f"📊 Production models: {len(main_models)}")
    print(f"🧪 API test models: {len(api_models)}")

    missing_in_api = main_models - api_models
    extra_in_api = api_models - main_models

    if missing_in_api:
        print(f"\n⚠️  Models missing from API conftest: {missing_in_api}")
        print("   These may cause 'no such table' errors if API tests use them.")

    if extra_in_api:
        print(f"\n🧹 Extra models in API conftest: {extra_in_api}")
        print("   These are OK - API conftest can have models not in production.")

    if not missing_in_api and not extra_in_api:
        print("\n✅ All models are properly synchronized!")

    print(f"\n📋 Shared models ({len(api_models & main_models)}):")
    for model in sorted(api_models & main_models):
        print(f"   ✅ {model}")

    if missing_in_api:
        print("\n💡 To fix missing models, add them to /tests/api/conftest.py")
        print("   Follow the SQLite compatibility patterns shown in the file.")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
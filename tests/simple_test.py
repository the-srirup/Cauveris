#!/usr/bin/env python3
"""
Minimal test to verify basic Cauveris structure
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_structure():
    """Test that the basic directory structure and key files exist"""
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Check backend structure
    required_dirs = [
        'cauveris',
        'cauveris/api',
        'cauveris/schemas',
        'cauveris/ingestion',
        'cauveris/timeline',
        'cauveris/hypothesis',
        'cauveris/sandbox',
        'cauveris/simulation',
        'cauveris/patch',
        'cauveris/verifier',
        'cauveris/report',
        'cauveris/model_gateway',
        'cauveris/state_machine',
        'cauveris/datasets',
        'apps/web/app'
    ]

    missing_dirs = []
    for dir_path in required_dirs:
        full_path = os.path.join(base_path, dir_path)
        if not os.path.isdir(full_path):
            missing_dirs.append(dir_path)

    if missing_dirs:
        print(f"✗ Missing directories: {missing_dirs}")
        return False
    else:
        print("✓ All required directories exist")

    # Check key files
    required_files = [
        'cauveris/config.py',
        'cauveris/main.py',
        'cauveris/api/main.py',
        'cauveris/schemas/incident.py',
        'cauveris/schemas/hypothesis.py',
        'cauveris/schemas/patch.py',
        'cauveris/model_gateway/local.py',
        'cauveris/model_gateway/nebius.py',
        'cauveris/state_machine/orchestrator.py',
        'cauveris/datasets/golden_incident.py',
        'pyproject.toml',
        'README.md',
        'apps/web/app/layout.tsx',
        'apps/web/app/page.tsx',
        'apps/web/app/reality-rewind/page.tsx',
        'apps/web/app/causal-constellation/page.tsx',
        'apps/web/app/ghost-lab/page.tsx',
        'apps/web/app/patch-forge/page.tsx',
        'apps/web/app/victory-replay/page.tsx',
        'apps/web/app/evidence-vault/page.tsx'
    ]

    missing_files = []
    for file_path in required_files:
        full_path = os.path.join(base_path, file_path)
        if not os.path.isfile(full_path):
            missing_files.append(file_path)

    if missing_files:
        print(f"✗ Missing files: {missing_files}")
        return False
    else:
        print("✓ All required files exist")

    # Check that key files are not empty
    empty_files = []
    for file_path in required_files[:10]:  # Check first 10 files
        full_path = os.path.join(base_path, file_path)
        if os.path.getsize(full_path) == 0:
            empty_files.append(file_path)

    if empty_files:
        print(f"⚠ Warning: Empty files: {empty_files}")
    else:
        print("✓ Key files are not empty")

    assert len(missing_dirs) == 0, f"Missing directories: {missing_dirs}"
    assert len(missing_files) == 0, f"Missing files: {missing_files}"

if __name__ == "__main__":
    if test_basic_structure():
        print("\n✓ Basic structure test PASSED")
        print("The Cauveris project structure is ready for implementation completion.")
        sys.exit(0)
    else:
        print("\n✗ Basic structure test FAILED")
        print("Please check the missing directories and files above.")
        sys.exit(1)

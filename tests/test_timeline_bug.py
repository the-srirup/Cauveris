#!/usr/bin/env python3
"""
Test script to reproduce the timeline builder bug.
"""
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cauveris.schemas.incident import Incident
from cauveris.timeline.builder import TimelineBuilder
from pathlib import Path

async def test_timeline_builder_with_missing_bundle():
    """Test timeline builder when bundle directory doesn't exist."""
    print("Testing timeline builder with missing bundle directory...")

    # Create an incident
    incident = Incident(title="Test Incident")
    print(f"Created incident: {incident.id}")
    print(f"Incident type: {type(incident)}")
    print(f"Has timeline_events attribute: {hasattr(incident, 'timeline_events')}")

    # Check initial value
    print(f"Initial timeline_events: {incident.timeline_events}")

    # Create timeline builder
    builder = TimelineBuilder()
    print(f"Created timeline builder: {type(builder)}")

    # Temporarily rename the bundle directory to simulate it missing
    bundle_path = Path("./incident-CAU-0001")
    if bundle_path.exists():
        print(f"Bundle directory exists at: {bundle_path.absolute()}")
        # Rename it temporarily
        temp_path = Path("./incident-CAU-0001.temp")
        if temp_path.exists():
            import shutil
            shutil.rmtree(temp_path)
        bundle_path.rename(temp_path)
        print(f"Renamed bundle directory to: {temp_path.absolute()}")
    else:
        print(f"Bundle directory does not exist at: {bundle_path.absolute()}")

    try:
        # This should trigger the "Bundle directory not found" path
        result = await builder.build(incident)
        print(f"Build succeeded. Result type: {type(result)}")
        print(f"Result timeline_events: {result.timeline_events}")
        print(f"Result timeline_events length: {len(result.timeline_events)}")
    except Exception as e:
        print(f"ERROR during build: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Restore the bundle directory
        temp_path = Path("./incident-CAU-0001.temp")
        bundle_path = Path("./incident-CAU-0001")
        if temp_path.exists():
            if bundle_path.exists():
                import shutil
                shutil.rmtree(bundle_path)
            temp_path.rename(bundle_path)
            print(f"Restored bundle directory to: {bundle_path.absolute()}")

if __name__ == "__main__":
    asyncio.run(test_timeline_builder_with_missing_bundle())

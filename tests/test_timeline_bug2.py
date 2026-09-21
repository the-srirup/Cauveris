#!/usr/bin/env python3
"""
Test script to reproduce the timeline builder bug with present bundle.
"""
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cauveris.schemas.incident import Incident
from cauveris.timeline.builder import TimelineBuilder
from pathlib import Path

async def test_timeline_builder_with_present_bundle():
    """Test timeline builder when bundle directory exists but has issues."""
    print("Testing timeline loader with present bundle directory...")

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

    # Check that bundle directory exists
    bundle_path = Path("./incident-CAU-0001")
    if bundle_path.exists():
        print(f"Bundle directory exists at: {bundle_path.absolute()}")
        # List contents
        print("Contents:")
        for item in bundle_path.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(bundle_path)
                print(f"  {rel_path}")
    else:
        print(f"Bundle directory does not exist at: {bundle_path.absolute()}")

    try:
        # This should go through the normal parsing path
        result = await builder.build(incident)
        print(f"Build succeeded. Result type: {type(result)}")
        print(f"Result timeline_events: {result.timeline_events}")
        print(f"Result timeline_events length: {len(result.timeline_events)}")

        # Check if timeline_events is properly set
        if hasattr(result, 'timeline_events'):
            print("Result has timeline_events attribute: True")
            print(f"Result timeline_events value: {result.timeline_events}")
        else:
            print("Result has timeline_events attribute: False")

    except Exception as e:
        print(f"ERROR during build: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_timeline_builder_with_present_bundle())

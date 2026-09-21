#!/usr/bin/env python3
"""
Test script to mimic the exact orchestrator snippet that fails.
"""
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cauveris.schemas.incident import Incident
from cauveris.timeline.builder import TimelineBuilder
from cauveris.ingestion.controller import IngestionController

async def test_orchestrator_snippet():
    """Mimic the exact code from orchestrator that's failing."""
    print("Testing orchestrator snippet...")

    # Create an incident (simulating what comes from ingestion)
    incident = Incident(title="Test Incident")
    print(f"Created incident: {incident.id}")
    print(f"Incident type: {type(incident)}")
    print(f"Incident module: {type(incident).__module__}")
    print(f"Has timeline_events: {hasattr(incident, 'timeline_events')}")
    print(f"Initial timeline_events: {incident.timeline_events}")

    # Simulate what ingestion does (just pass it through for now)
    ingestion = IngestionController()
    print(f"Created ingestion controller: {type(ingestion)}")

    # This corresponds to line 98 in orchestrator: context.incident = await self.ingestion.process(context.incident)
    validated_incident = await ingestion.process(incident)
    print(f"After ingestion - incident type: {type(validated_incident)}")
    print(f"After ingestion - has timeline_events: {hasattr(validated_incident, 'timeline_events')}")
    print(f"After ingestion - timeline_events: {validated_incident.timeline_events}")

    # This corresponds to line 101 in orchestrator: context.validated_incident = await self.timeline_builder.build(context.incident)
    timeline_builder = TimelineBuilder()
    print(f"Created timeline builder: {type(timeline_builder)}")

    try:
        result = await timeline_builder.build(validated_incident)
        print("Timeline build succeeded!")
        print(f"Result type: {type(result)}")
        print(f"Result has timeline_events: {hasattr(result, 'timeline_events')}")
        print(f"Result timeline_events length: {len(result.timeline_events) if result.timeline_events else 0}")
    except Exception as e:
        print(f"ERROR in timeline builder: {e}")
        import traceback
        traceback.print_exc()

        # Let's debug the incident object right before the failure
        print("\n=== DEBUGGING INCIDENT OBJECT ===")
        print(f"Incident ID: {validated_incident.id}")
        print(f"Incident type: {type(validated_incident)}")
        print(f"Incident module: {type(validated_incident).__module__}")
        print(f"Has timeline_events attr: {hasattr(validated_incident, 'timeline_events')}")

        if hasattr(validated_incident, '__dict__'):
            print(f"Incident __dict__ keys: {list(validated_incident.__dict__.keys())}")
            if 'timeline_events' in validated_incident.__dict__:
                print(f"timeline_events in __dict__: {validated_incident.__dict__['timeline_events']}")
            else:
                print("timeline_events NOT in __dict__")

        print(f"Dir contains timeline_events: {'timeline_events' in dir(validated_incident)}")

        # Try to get the attribute directly
        try:
            attr_value = getattr(validated_incident, 'timeline_events', 'NO_SUCH_ATTRIBUTE')
            print(f"getattr(timeline_events): {attr_value}")
        except Exception as attr_e:
            print(f"Error getting timeline_events attr: {attr_e}")

if __name__ == "__main__":
    asyncio.run(test_orchestrator_snippet())

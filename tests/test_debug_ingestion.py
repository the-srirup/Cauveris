#!/usr/bin/env python3
"""
Debug script to check what happens to Incident object during ingestion.
"""
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cauveris.schemas.incident import Incident
from cauveris.ingestion.controller import IngestionController
from cauveris.timeline.builder import TimelineBuilder

async def test_incident_after_ingestion():
    """Test what happens to incident object after ingestion."""
    print('=' * 60)
    print('Testing Incident object through ingestion pipeline')
    print('=' * 60)

    # Create a basic incident
    original_incident = Incident(title='Test Incident')
    print('1. Original incident created:')
    print(f'   Type: {type(original_incident)}')
    print(f'   Module: {type(original_incident).__module__}')
    print(f'   Has timeline_events: {hasattr(original_incident, "timeline_events")}')
    print(f'   timeline_events value: {original_incident.timeline_events}')
    print(f'   ID: {original_incident.id}')

    # Check the __dict__ to see what's actually stored
    print(f'   __dict__ keys: {list(original_incident.__dict__.keys())}')
    if 'timeline_events' in original_incident.__dict__:
        print(f'   timeline_events in __dict__: {original_incident.__dict__["timeline_events"]}')

    # Run ingestion
    print('\n2. Running ingestion...')
    ingestion = IngestionController()
    try:
        processed_incident = await ingestion.process(original_incident)
        print('   Ingestion completed successfully')
        print(f'   Returned incident type: {type(processed_incident)}')
        print(f'   Returned incident module: {type(processed_incident).__module__}')
        print(f'   Has timeline_events: {hasattr(processed_incident, "timeline_events")}')
        print(f'   timeline_events value: {processed_incident.timeline_events}')
        print(f'   ID: {processed_incident.id}')
        print(f'   Same object? {original_incident is processed_incident}')

        # Check the __dict__
        print(f'   __dict__ keys: {list(processed_incident.__dict__.keys())}')
        if 'timeline_events' in processed_incident.__dict__:
            print(f'   timeline_events in __dict__: {processed_incident.__dict__["timeline_events"]}')

    except Exception as e:
        print(f'   ERROR during ingestion: {e}')
        import traceback
        traceback.print_exc()
        return

    # Test timeline builder
    print('\n3. Testing timeline builder...')
    try:
        builder = TimelineBuilder()
        result = await builder.build(processed_incident)
        print('   Timeline build SUCCESS')
        print(f'   Result type: {type(result)}')
        print(f'   Has timeline_events: {hasattr(result, "timeline_events")}')
        print(f'   timeline_events length: {len(result.timeline_events) if result.timeline_events else 0}')
    except Exception as e:
        print(f'   ERROR during timeline builder: {e}')
        print(f'   Error type: {type(e)}')
        import traceback
        traceback.print_exc()

        # Debug the processed incident right before failure
        print('\n4. DEBUGGING processed incident:')
        print(f'   Type: {type(processed_incident)}')
        print(f'   Module: {type(processed_incident).__module__}')
        print(f'   Has timeline_events: {hasattr(processed_incident, "timeline_events")}')
        if hasattr(processed_incident, '__dict__'):
            print(f'   __dict__ keys: {list(processed_incident.__dict__.keys())}')
            print(f'   "timeline_events" in __dict__: {"timeline_events" in processed_incident.__dict__}')
        print(f'   Dir contains timeline_events: {"timeline_events" in dir(processed_incident)}')

if __name__ == '__main__':
    asyncio.run(test_incident_after_ingestion())

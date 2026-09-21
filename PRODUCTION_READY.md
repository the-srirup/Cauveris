# Cauveris - Production Ready Release

## Overview
This repository contains the Cauveris autonomous reality debugger for AI-powered robotic systems, organized for production deployment and open source contribution.

Please see the individual files and directories for detailed information about the codebase structure and functionality.

Key directories include:
- cauveris/ - Main source code
- apps/ - Frontend applications
- docs/ - Documentation
- tests/ - Test suite
- golden_incident/ - Sample incident data
- scripts/ - Utility scripts

See README.md for setup and usage instructions.

This release includes fixes for 5 critical bugs identified during systematic audit:
1. Verification Engine mkdir() errors - Added exist_ok=True
2. Security validate_file_type MIME/type mismatch - Fixed extension-to-MIME mapping
3. API Incident.EvidenceItem AttributeError - Fixed import and usage
4. Report Generator timeline field reference - Corrected to use timeline_events
5. Orchestrator timeline field type mismatch - Updated PipelineContext

For more details, see docs/BUGFIX_SUMMARY.md


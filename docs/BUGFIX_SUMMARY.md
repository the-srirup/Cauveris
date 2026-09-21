# Bug Fix Summary

## Fixed Bugs

### 1. Verification Engine mkdir() errors
- **Location**: `cauveris/verifier/engine.py`
- **Issues**: Multiple `mkdir()` calls missing `exist_ok=True` causing "[WinError 183] Cannot create a file when that file already exists" on subsequent runs
- **Fixes**: Added `exist_ok=True` to:
  - Line 127: `src_dir.mkdir(exist_ok=True)`
  - Line 129: `config_dir.mkdir(exist_ok=True)`
  - Line 177: Second `src_dir.mkdir(exist_ok=True)` (duplicate call)

### 2. Security validate_file_type MIME/type mismatch
- **Location**: `cauveris/security.py`
- **Issue**: `validate_file_type` was receiving MIME type strings (like "application/json") but comparing to file extension set ({'.json', '.csv'})
- **Fix**: Changed function to accept `allowed_mime_types` set and added extension-to-MIME mapping for proper validation

### 3. API Incident.EvidenceItem AttributeError
- **Location**: `cauveris/api/main.py`
- **Issue**: Attempted to use `Incident.EvidenceItem` which doesn't exist; should import `EvidenceItem` directly
- **Fix**: 
  - Added explicit `EvidenceItem` import
  - Changed `Incident.EvidenceItem(...)` to `EvidenceItem(...)`

### 4. Report Generator timeline field reference
- **Location**: `cauveris/report/generator.py`
- **Issue**: Line referenced `incident.timeline` but Incident class defines `timeline_events`
- **Fix**: Changed `getattr(incident, 'timeline', {})` to `getattr(incident, 'timeline_events', [])`

### 5. Orchestrator timeline field type mismatch
- **Location**: `cauveris/state_machine/orchestrator.py`
- **Issue**: PipelineContext had `timeline: Optional[Any] = None` but timeline is now stored directly on Incident as `timeline_events`
- **Fix**: 
  - Removed incorrect `timeline` field
  - Added `timeline_events: Optional[List[Dict[str, Any]]] = None` with appropriate comment

## Verification
- Ran `test_debug_ingestion.py` successfully - ingestion pipeline works and timeline builder produces 24 events when bundle directory exists
- All fixes address root causes identified during systematic file-by-file audit

## Tasks Completed
1. [completed] Audit core config/main/security
2. [completed] Audit model_gateway
3. [completed] Audit ingestion/timeline/hypothesis
4. [completed] Audit verifier/patch/sandbox
5. [completed] Audit simulation/report/api/orchestrator
6. [completed] Fix confirmed bugs

The Cauveris codebase has been debugged and is ready for further development.
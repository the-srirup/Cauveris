"""
End-to-end flow test for Cauveris Mission Control.
Executes against live FastAPI backend at http://127.0.0.1:8000.
"""
import urllib.request
import json
import time

BASE = "http://127.0.0.1:8000/api/v1"

def post(url, data=None):
    body = json.dumps(data).encode("utf-8") if data else b""
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode("utf-8"))

def get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode("utf-8"))

def run():
    print("=== 1. Load Golden Incident ===")
    load_res = post(f"{BASE}/incidents?golden=true")
    print(f"Loaded: {load_res['incident_id']} (is_demo: {load_res.get('is_demonstration')})")
    assert load_res["incident_id"] == "CAU-0001"
    assert load_res.get("is_demonstration") is True

    print("\n=== 2. Validate Evidence ===")
    val_res = post(f"{BASE}/incidents/CAU-0001/validate")
    print(f"Evidence count: {val_res['evidence_count']}, Valid: {val_res['validation_status']}, Secrets: {val_res['secrets_detected_count']}")
    assert val_res["checksums_valid"] is True

    print("\n=== 3. Initial Stage Graph ===")
    init_events = get(f"{BASE}/incidents/CAU-0001/events")
    print(f"Initial State: {init_events['state']}, Progress: {init_events['progress']}")
    assert len(init_events["stages"]) == 9
    assert all(s["status"] == "PENDING" for s in init_events["stages"])

    print("\n=== 4. Start Investigation ===")
    start_res = post(f"{BASE}/incidents/CAU-0001/reconstruct")
    print(f"Start Result: {start_res['message']} (State: {start_res['pipeline_state']})")
    assert start_res["pipeline_state"] == "RUNNING"

    print("\n=== 5. Duplicate Start Prevention ===")
    try:
        _dup_res = post(f"{BASE}/incidents/CAU-0001/reconstruct")
        print("ERROR: Duplicate request was not blocked!")
    except urllib.error.HTTPError as e:
        print(f"SUCCESS: Blocked duplicate start with HTTP {e.code}")
        assert e.code == 409

    print("\n=== 6. Monitoring Live Stage Progress ===")
    terminal_states = {"SUCCESS", "COMPLETED", "FAILED", "CANCELLED", "DEGRADED"}
    last_active = None
    start_time = time.time()
    while True:
        events = get(f"{BASE}/incidents/CAU-0001/events")
        curr_state = events["state"]
        active_st = events.get("active_stage_id")
        if active_st != last_active:
            print(f"  Progress: {int(events['progress']*100)}% | Active Stage: {active_st} | Pipeline State: {curr_state}")
            last_active = active_st
        if curr_state in terminal_states:
            print(f"\nTERMINAL STATE REACHED: {curr_state} in {time.time()-start_time:.2f}s")
            assert curr_state == "SUCCESS"
            for s in events["stages"]:
                print(f"  [OK] {s['name']}: {s['status']} ({s.get('duration_ms', 0)}ms)")
            break
        time.sleep(0.4)

    print("\n=== 7. Reset Demo ===")
    reset_res = post(f"{BASE}/incidents/CAU-0001/reset")
    print(f"Reset Result: {reset_res['message']} (State: {reset_res['state']})")
    assert reset_res["state"] == "IDLE"

    post_reset = get(f"{BASE}/incidents/CAU-0001/events")
    print(f"Post-Reset State: {post_reset['state']}, Stage statuses: {set(s['status'] for s in post_reset['stages'])}")
    assert post_reset["state"] == "IDLE"
    assert all(s["status"] == "PENDING" for s in post_reset["stages"])

    print("\n=== ALL END-TO-END FLOW CHECKS PASSED! ===")

if __name__ == "__main__":
    run()

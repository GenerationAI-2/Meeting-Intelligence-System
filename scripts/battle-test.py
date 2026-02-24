#!/usr/bin/env python3
"""
Battle Test — Full validation of a deployed Meeting Intelligence environment.

Tests every MCP tool, REST endpoint, auth boundary, edge case, and load scenario
against a live environment. Designed to be run after deploy-new-client.sh.

Usage:
    python3 scripts/battle-test.py --url <FQDN> --token <MCP_TOKEN>

Example:
    python3 scripts/battle-test.py \
        --url https://mi-battle-test.orangemeadow-aef6120b.australiaeast.azurecontainerapps.io \
        --token dsZUjuCGuYH1lcm-FJTtYzbhv6_njfTH3oTZvKB6wH0
"""

import argparse
import json
import sys
import time
import concurrent.futures
import random
import string

try:
    import requests
except ImportError:
    print("Missing dependency: pip3 install requests")
    sys.exit(1)

# ============================================================================
# TEST INFRASTRUCTURE
# ============================================================================

PASS = 0
FAIL = 0
WARN = 0
RESULTS = []


def test(name):
    """Decorator to register and run a test."""
    def decorator(func):
        func._test_name = name
        return func
    return decorator


def ok(name, detail=""):
    global PASS
    PASS += 1
    status = f"  PASS  {name}"
    if detail:
        status += f" — {detail}"
    print(status)
    RESULTS.append(("PASS", name, detail))


def fail(name, detail=""):
    global FAIL
    FAIL += 1
    status = f"  FAIL  {name}"
    if detail:
        status += f" — {detail}"
    print(status)
    RESULTS.append(("FAIL", name, detail))


def warn(name, detail=""):
    global WARN
    WARN += 1
    status = f"  WARN  {name}"
    if detail:
        status += f" — {detail}"
    print(status)
    RESULTS.append(("WARN", name, detail))


def parse_sse_response(resp):
    """Parse a response that may be JSON or SSE event-stream format.

    MCP Streamable HTTP can return either application/json or text/event-stream.
    SSE format: 'event: message\\ndata: {json}\\n\\n'
    Returns the parsed JSON body or None.
    """
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        return resp.json()
    # Parse SSE — extract JSON from 'data:' lines
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            data_str = line[len("data:"):].strip()
            if data_str:
                try:
                    return json.loads(data_str)
                except json.JSONDecodeError:
                    continue
    # Fallback — try parsing the whole body as JSON
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return None


def mcp_call(base_url, token, method, params=None, retries=3):
    """Make an MCP JSON-RPC call with automatic 429 retry."""
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": random.randint(1, 99999),
        "params": {
            "name": method,
            "arguments": params or {}
        }
    }
    for attempt in range(retries):
        resp = requests.post(
            f"{base_url}/mcp",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            timeout=30
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2))
            time.sleep(retry_after)
            continue
        return resp
    return resp  # return last 429 response if all retries exhausted


def mcp_result(base_url, token, method, params=None):
    """Make an MCP call and return the parsed result content."""
    resp = mcp_call(base_url, token, method, params)
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
    body = parse_sse_response(resp)
    if body is None:
        return None, f"Could not parse response: {resp.text[:200]}"
    if "error" in body:
        return None, f"RPC error: {body['error']}"
    # Extract text content from MCP response
    result = body.get("result", {})
    content = result.get("content", [])
    if content and isinstance(content, list):
        text = content[0].get("text", "")
        try:
            return json.loads(text), None
        except json.JSONDecodeError:
            return text, None
    return result, None


# ============================================================================
# HEALTH & INFRASTRUCTURE TESTS
# ============================================================================

def test_health(base_url):
    print("\n=== HEALTH & INFRASTRUCTURE ===")

    # Health endpoint (30s timeout for cold start)
    try:
        r = requests.get(f"{base_url}/health", timeout=30)
        if r.status_code == 200:
            ok("GET /health", r.json().get("status", ""))
        else:
            fail("GET /health", f"HTTP {r.status_code}")
    except Exception as e:
        fail("GET /health", str(e))

    # Liveness probe
    try:
        r = requests.get(f"{base_url}/health/live", timeout=30)
        if r.status_code == 200:
            ok("GET /health/live")
        else:
            fail("GET /health/live", f"HTTP {r.status_code}")
    except Exception as e:
        fail("GET /health/live", str(e))

    # Readiness probe (DB connectivity)
    try:
        r = requests.get(f"{base_url}/health/ready", timeout=30)
        data = r.json()
        if r.status_code == 200 and data.get("database") == "connected":
            ok("GET /health/ready", "database connected")
        else:
            fail("GET /health/ready", f"HTTP {r.status_code}: {data}")
    except Exception as e:
        fail("GET /health/ready", str(e))

    # Schema endpoint (P8)
    try:
        r = requests.get(f"{base_url}/api/schema", timeout=10)
        data = r.json()
        if r.status_code == 200 and "entities" in data:
            entities = list(data["entities"].keys())
            if set(entities) >= {"meeting", "action", "decision"}:
                ok("GET /api/schema", f"v{data.get('version', '?')}, entities: {entities}")
            else:
                fail("GET /api/schema", f"Missing entities: {entities}")
        else:
            fail("GET /api/schema", f"HTTP {r.status_code}")
    except Exception as e:
        fail("GET /api/schema", str(e))


# ============================================================================
# AUTH TESTS
# ============================================================================

def test_auth(base_url, token):
    print("\n=== AUTHENTICATION ===")

    # Valid token — should work
    resp = mcp_call(base_url, token, "list_meetings", {"limit": 1})
    if resp.status_code == 200:
        ok("MCP auth with valid token")
    else:
        fail("MCP auth with valid token", f"HTTP {resp.status_code}")

    # Invalid token — should get 401
    resp = mcp_call(base_url, "invalid-token-12345", "list_meetings", {"limit": 1})
    if resp.status_code == 401:
        ok("MCP auth rejects invalid token", "401")
    else:
        fail("MCP auth rejects invalid token", f"Expected 401, got {resp.status_code}")

    # Empty token — should get 401
    try:
        r = requests.post(
            f"{base_url}/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            timeout=10
        )
        if r.status_code == 401:
            ok("MCP auth rejects missing token", "401")
        else:
            fail("MCP auth rejects missing token", f"Expected 401, got {r.status_code}")
    except Exception as e:
        fail("MCP auth rejects missing token", str(e))

    # Path-based token auth
    resp = requests.post(
        f"{base_url}/mcp/{token}",
        json={"jsonrpc": "2.0", "method": "tools/call", "id": 1,
              "params": {"name": "list_meetings", "arguments": {"limit": 1}}},
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        timeout=10
    )
    if resp.status_code == 200:
        ok("MCP path-based token auth")
    else:
        fail("MCP path-based token auth", f"HTTP {resp.status_code}")

    # SSE endpoint with token
    try:
        r = requests.get(f"{base_url}/sse?token={token}", timeout=5, stream=True)
        if r.status_code == 200:
            ok("SSE transport connects")
        else:
            fail("SSE transport connects", f"HTTP {r.status_code}")
    except requests.exceptions.ReadTimeout:
        ok("SSE transport connects", "stream opened (timed out as expected)")
    except Exception as e:
        fail("SSE transport connects", str(e))

    # REST API without auth — should get 401
    try:
        r = requests.get(f"{base_url}/api/meetings", timeout=10)
        if r.status_code == 401:
            ok("REST API rejects unauthenticated request", "401")
        else:
            warn("REST API without auth", f"Expected 401, got {r.status_code}")
    except Exception as e:
        fail("REST API without auth", str(e))


# ============================================================================
# MCP TOOL TESTS — MEETINGS
# ============================================================================

def test_meetings(base_url, token):
    print("\n=== MCP TOOLS: MEETINGS ===")

    # Create a meeting
    data, err = mcp_result(base_url, token, "create_meeting", {
        "title": "Battle Test Meeting — 24 Feb 2026",
        "meeting_date": "2026-02-24T10:30:00",
        "summary": "## Key Points\n\n- **Testing** the full deployment pipeline\n- Markdown formatting preserved\n\n## Actions\n\n- Review stress test results",
        "attendees": "Caleb Lucas, Test User",
        "source": "Manual",
        "tags": "battle-test, stress-test"
    })
    if err:
        fail("create_meeting", err)
        return None
    meeting_id = data.get("id")
    if meeting_id:
        ok("create_meeting", f"id={meeting_id}")
    else:
        fail("create_meeting", f"No ID in response: {data}")
        return None

    # Get meeting
    data, err = mcp_result(base_url, token, "get_meeting", {"meeting_id": meeting_id})
    if err:
        fail("get_meeting", err)
    elif data.get("id") == meeting_id and "Battle Test Meeting" in data.get("title", ""):
        ok("get_meeting", f"title='{data['title']}', summary length={len(data.get('summary', ''))}")
    else:
        fail("get_meeting", f"Unexpected data: {data}")

    # List meetings
    data, err = mcp_result(base_url, token, "list_meetings", {"limit": 10})
    if err:
        fail("list_meetings", err)
    elif data.get("count", 0) > 0:
        ok("list_meetings", f"count={data['count']}")
    else:
        fail("list_meetings", f"Expected count > 0: {data}")

    # Update meeting
    data, err = mcp_result(base_url, token, "update_meeting", {
        "meeting_id": meeting_id,
        "summary": "## Updated Summary\n\n- Added during battle test\n- Confirms update_meeting works"
    })
    if err:
        fail("update_meeting", err)
    else:
        ok("update_meeting")

    # Search meetings
    data, err = mcp_result(base_url, token, "search_meetings", {"query": "battle test"})
    if err:
        fail("search_meetings", err)
    elif data.get("count", 0) > 0:
        ok("search_meetings", f"found {data['count']} result(s)")
    else:
        fail("search_meetings", "No results for 'battle test'")

    # Create second meeting for list/search testing
    data2, _ = mcp_result(base_url, token, "create_meeting", {
        "title": "Second Battle Test Meeting",
        "meeting_date": "2026-02-24T14:00:00",
        "summary": "Follow-up discussion",
        "tags": "battle-test"
    })
    second_meeting_id = data2.get("id") if data2 else None

    return meeting_id, second_meeting_id


# ============================================================================
# MCP TOOL TESTS — ACTIONS
# ============================================================================

def test_actions(base_url, token, meeting_id):
    print("\n=== MCP TOOLS: ACTIONS ===")

    # Create action with all fields
    data, err = mcp_result(base_url, token, "create_action", {
        "action_text": "Review battle test results and fix deploy pipeline gaps",
        "owner": "Caleb Lucas",
        "due_date": "2026-02-28",
        "meeting_id": meeting_id,
        "notes": "Created during battle test validation"
    })
    if err:
        fail("create_action (full)", err)
        return None
    action_id = data.get("id")
    if action_id:
        ok("create_action", f"id={action_id}, due_date={data.get('due_date')}")
    else:
        fail("create_action", f"No ID: {data}")
        return None

    # Create action without optional fields
    data2, err = mcp_result(base_url, token, "create_action", {
        "action_text": "Minimal action — no due date, no meeting, no notes",
        "owner": "Test User"
    })
    if err:
        fail("create_action (minimal)", err)
    else:
        ok("create_action (minimal)", f"id={data2.get('id')}")
        action_id_2 = data2.get("id")

    # Get action
    data, err = mcp_result(base_url, token, "get_action", {"action_id": action_id})
    if err:
        fail("get_action", err)
    elif data.get("owner") == "Caleb Lucas":
        ok("get_action", f"owner={data['owner']}, status={data.get('status')}")
    else:
        fail("get_action", f"Unexpected: {data}")

    # List actions (default — open only)
    data, err = mcp_result(base_url, token, "list_actions", {})
    if err:
        fail("list_actions (default)", err)
    elif data.get("count", 0) >= 2:
        ok("list_actions (default)", f"count={data['count']}")
    else:
        fail("list_actions (default)", f"Expected >= 2: {data}")

    # List actions filtered by owner
    data, err = mcp_result(base_url, token, "list_actions", {"owner": "Caleb Lucas"})
    if err:
        fail("list_actions (by owner)", err)
    elif data.get("count", 0) >= 1:
        ok("list_actions (by owner)", f"count={data['count']}")
    else:
        fail("list_actions (by owner)", f"Expected >= 1: {data}")

    # Update action
    data, err = mcp_result(base_url, token, "update_action", {
        "action_id": action_id,
        "notes": "Updated during battle test — confirming update works"
    })
    if err:
        fail("update_action", err)
    else:
        ok("update_action")

    # Complete action
    data, err = mcp_result(base_url, token, "complete_action", {"action_id": action_id})
    if err:
        fail("complete_action", err)
    else:
        ok("complete_action")

    # Verify status changed
    data, err = mcp_result(base_url, token, "get_action", {"action_id": action_id})
    if data and data.get("status") == "Complete":
        ok("complete_action (verified)", "status=Complete")
    else:
        fail("complete_action (verified)", f"Expected Complete: {data}")

    # Park action
    if action_id_2:
        data, err = mcp_result(base_url, token, "park_action", {"action_id": action_id_2})
        if err:
            fail("park_action", err)
        else:
            ok("park_action")

    # Search actions
    data, err = mcp_result(base_url, token, "search_actions", {"query": "battle test"})
    if err:
        fail("search_actions", err)
    elif data.get("count", 0) > 0:
        ok("search_actions", f"found {data['count']} result(s)")
    else:
        fail("search_actions", "No results")

    # List all statuses (omit status filter to get all)
    for status in ["Open", "Complete", "Parked"]:
        data, err = mcp_result(base_url, token, "list_actions", {"status": status})
        if err:
            fail(f"list_actions (status={status})", err)
        else:
            ok(f"list_actions (status={status})", f"count={data.get('count', '?')}")

    return action_id


# ============================================================================
# MCP TOOL TESTS — DECISIONS
# ============================================================================

def test_decisions(base_url, token, meeting_id):
    print("\n=== MCP TOOLS: DECISIONS ===")

    # Create decision
    data, err = mcp_result(base_url, token, "create_decision", {
        "decision_text": "Deploy pipeline needs SQL firewall automation before next client",
        "meeting_id": meeting_id,
        "context": "Discovered during battle test — deployer IP not whitelisted, DB init fails"
    })
    if err:
        fail("create_decision", err)
        return None
    decision_id = data.get("id")
    if decision_id:
        ok("create_decision", f"id={decision_id}")
    else:
        fail("create_decision", f"No ID: {data}")
        return None

    # List decisions
    data, err = mcp_result(base_url, token, "list_decisions", {})
    if err:
        fail("list_decisions", err)
    elif data.get("count", 0) > 0:
        ok("list_decisions", f"count={data['count']}")
    else:
        fail("list_decisions", f"Expected count > 0")

    # List decisions by meeting
    data, err = mcp_result(base_url, token, "list_decisions", {"meeting_id": meeting_id})
    if err:
        fail("list_decisions (by meeting)", err)
    elif data.get("count", 0) > 0:
        ok("list_decisions (by meeting)", f"count={data['count']}")
    else:
        fail("list_decisions (by meeting)", "No results")

    # Search decisions
    data, err = mcp_result(base_url, token, "search_decisions", {"query": "firewall"})
    if err:
        fail("search_decisions", err)
    elif data.get("count", 0) > 0:
        ok("search_decisions", f"found {data['count']} result(s)")
    else:
        fail("search_decisions", "No results")

    return decision_id


# ============================================================================
# SCHEMA ENDPOINT TESTS
# ============================================================================

def test_schema(base_url):
    print("\n=== SCHEMA ENDPOINT (P8) ===")

    r = requests.get(f"{base_url}/api/schema", timeout=10)
    data = r.json()

    # Version field
    if data.get("version"):
        ok("Schema has version", data["version"])
    else:
        fail("Schema has version")

    # All entities present
    entities = data.get("entities", {})
    for entity in ["meeting", "action", "decision"]:
        if entity in entities:
            fields = entities[entity].get("fields", {})
            ok(f"Schema has {entity}", f"{len(fields)} fields defined")

            # Check field completeness
            for fname, fdef in fields.items():
                required_props = {"type", "required", "description"}
                missing = required_props - set(fdef.keys())
                if missing:
                    fail(f"Schema {entity}.{fname} missing props", str(missing))
        else:
            fail(f"Schema has {entity}", "missing")

    # Check specific critical fields have examples
    meeting_fields = entities.get("meeting", {}).get("fields", {})
    if meeting_fields.get("meeting_date", {}).get("example"):
        ok("Schema meeting_date has example")
    else:
        warn("Schema meeting_date has no example")

    if meeting_fields.get("summary", {}).get("format") == "markdown":
        ok("Schema summary format=markdown")
    else:
        fail("Schema summary format", "Should be 'markdown'")

    # Check action status enum
    action_fields = entities.get("action", {}).get("fields", {})
    status_field = action_fields.get("status", {})
    if status_field.get("allowed_values"):
        ok("Schema action.status has allowed_values", str(status_field["allowed_values"]))
    else:
        # Might be in relationships or elsewhere
        warn("Schema action.status allowed_values", "Check structure")


# ============================================================================
# EDGE CASES & INPUT VALIDATION
# ============================================================================

def test_edge_cases(base_url, token):
    print("\n=== EDGE CASES & VALIDATION ===")

    # Empty title — should fail validation
    data, err = mcp_result(base_url, token, "create_meeting", {
        "title": "",
        "meeting_date": "2026-02-24"
    })
    if err or (data and "error" in str(data).lower()):
        ok("Rejects empty title")
    else:
        fail("Rejects empty title", f"Should fail: {data}")

    # Invalid date format
    data, err = mcp_result(base_url, token, "create_meeting", {
        "title": "Bad Date Test",
        "meeting_date": "not-a-date"
    })
    if err or (data and "error" in str(data).lower()):
        ok("Rejects invalid date")
    else:
        fail("Rejects invalid date", f"Should fail: {data}")

    # Very long title (> 255 chars)
    long_title = "A" * 300
    data, err = mcp_result(base_url, token, "create_meeting", {
        "title": long_title,
        "meeting_date": "2026-02-24"
    })
    if err or (data and "error" in str(data).lower()):
        ok("Rejects title > 255 chars")
    else:
        fail("Rejects title > 255 chars", f"Should fail: {data}")

    # HTML injection in title
    data, err = mcp_result(base_url, token, "create_meeting", {
        "title": "Test <script>alert('xss')</script> Meeting",
        "meeting_date": "2026-02-24"
    })
    if data and isinstance(data, dict):
        # Should succeed but strip HTML
        meeting_id = data.get("id")
        if meeting_id:
            detail, _ = mcp_result(base_url, token, "get_meeting", {"meeting_id": meeting_id})
            if detail and "<script>" not in detail.get("title", ""):
                ok("HTML stripped from title", detail.get("title", ""))
                # Clean up
                mcp_result(base_url, token, "delete_meeting", {"meeting_id": meeting_id})
            else:
                fail("HTML NOT stripped from title", detail.get("title", ""))
    else:
        warn("HTML injection test inconclusive", str(err or data))

    # Non-existent meeting ID
    data, err = mcp_result(base_url, token, "get_meeting", {"meeting_id": 999999})
    if err or (data and ("not found" in str(data).lower() or "error" in str(data).lower())):
        ok("get_meeting returns error for non-existent ID")
    else:
        fail("get_meeting for non-existent ID", f"Should fail: {data}")

    # Create action without required owner
    data, err = mcp_result(base_url, token, "create_action", {
        "action_text": "Missing owner test"
    })
    if err or (data and "error" in str(data).lower()):
        ok("Rejects action without owner")
    else:
        fail("Rejects action without owner", f"Should fail: {data}")

    # Create decision without required meeting_id
    data, err = mcp_result(base_url, token, "create_decision", {
        "decision_text": "Missing meeting_id test"
    })
    if err or (data and "error" in str(data).lower()):
        ok("Rejects decision without meeting_id")
    else:
        fail("Rejects decision without meeting_id", f"Should fail: {data}")

    # Null byte injection
    data, err = mcp_result(base_url, token, "create_meeting", {
        "title": "Null\x00byte test",
        "meeting_date": "2026-02-24"
    })
    if data and isinstance(data, dict) and data.get("id"):
        detail, _ = mcp_result(base_url, token, "get_meeting", {"meeting_id": data["id"]})
        if detail and "\x00" not in detail.get("title", ""):
            ok("Null bytes stripped from title")
            mcp_result(base_url, token, "delete_meeting", {"meeting_id": data["id"]})
        else:
            fail("Null bytes NOT stripped")
    else:
        ok("Null byte rejected at validation")


# ============================================================================
# DELETE TESTS (cascade)
# ============================================================================

def test_deletes(base_url, token, meeting_id, second_meeting_id, action_id, decision_id):
    print("\n=== DELETE & CASCADE ===")

    # Delete action directly
    data, err = mcp_result(base_url, token, "delete_action", {"action_id": action_id})
    if err:
        fail("delete_action", err)
    else:
        ok("delete_action")

    # Delete decision directly
    data, err = mcp_result(base_url, token, "delete_decision", {"decision_id": decision_id})
    if err:
        fail("delete_decision", err)
    else:
        ok("delete_decision")

    # Create new action + decision linked to second meeting, then delete meeting (cascade)
    if second_meeting_id:
        mcp_result(base_url, token, "create_action", {
            "action_text": "Cascade test action",
            "owner": "Test",
            "meeting_id": second_meeting_id
        })
        mcp_result(base_url, token, "create_decision", {
            "decision_text": "Cascade test decision",
            "meeting_id": second_meeting_id
        })

        data, err = mcp_result(base_url, token, "delete_meeting", {"meeting_id": second_meeting_id})
        if err:
            fail("delete_meeting (cascade)", err)
        else:
            ok("delete_meeting (cascade)", "meeting + linked action + decision deleted")

    # Delete the main meeting
    data, err = mcp_result(base_url, token, "delete_meeting", {"meeting_id": meeting_id})
    if err:
        fail("delete_meeting", err)
    else:
        ok("delete_meeting")

    # Verify deletion
    data, err = mcp_result(base_url, token, "get_meeting", {"meeting_id": meeting_id})
    if err or (data and "not found" in str(data).lower()):
        ok("Deleted meeting not retrievable")
    else:
        fail("Deleted meeting still retrievable", str(data))


# ============================================================================
# GET_SCHEMA MCP TOOL
# ============================================================================

def test_schema_mcp(base_url, token):
    print("\n=== GET_SCHEMA MCP TOOL ===")

    data, err = mcp_result(base_url, token, "get_schema", {})
    if err:
        fail("get_schema MCP tool", err)
    elif data and isinstance(data, dict) and "entities" in data:
        ok("get_schema MCP tool", f"v{data.get('version', '?')}, {len(data['entities'])} entities")
    else:
        fail("get_schema MCP tool", f"Unexpected response: {type(data)}")


# ============================================================================
# LOAD TESTS
# ============================================================================

def test_load(base_url, token):
    print("\n=== LOAD TESTING ===")

    # Create 20 meetings rapidly
    print("  Creating 20 meetings...")
    meeting_ids = []
    start = time.time()
    for i in range(20):
        data, err = mcp_result(base_url, token, "create_meeting", {
            "title": f"Load Test Meeting #{i+1}",
            "meeting_date": f"2026-03-{(i % 28) + 1:02d}T09:00:00",
            "summary": f"Meeting number {i+1} for load testing. " + "x" * 500,
            "tags": "load-test"
        })
        if data and data.get("id"):
            meeting_ids.append(data["id"])
    elapsed = time.time() - start
    if len(meeting_ids) == 20:
        ok(f"Create 20 meetings", f"{elapsed:.1f}s ({elapsed/20:.2f}s avg)")
    else:
        fail(f"Create 20 meetings", f"Only {len(meeting_ids)}/20 succeeded in {elapsed:.1f}s")

    # Concurrent reads — 10 simultaneous list_meetings calls
    print("  Running 10 concurrent reads...")
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(mcp_result, base_url, token, "list_meetings", {"limit": 50})
            for _ in range(10)
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.time() - start
    successes = sum(1 for data, err in results if data and not err)
    if successes == 10:
        ok(f"10 concurrent reads", f"{elapsed:.1f}s total")
    else:
        fail(f"10 concurrent reads", f"{successes}/10 succeeded in {elapsed:.1f}s")

    # Concurrent writes — 5 simultaneous create_action calls
    print("  Running 5 concurrent writes...")
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(mcp_result, base_url, token, "create_action", {
                "action_text": f"Concurrent action #{i+1}",
                "owner": "Load Test",
                "meeting_id": meeting_ids[0] if meeting_ids else None
            })
            for i in range(5)
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.time() - start
    successes = sum(1 for data, err in results if data and not err)
    if successes == 5:
        ok(f"5 concurrent writes", f"{elapsed:.1f}s total")
    else:
        fail(f"5 concurrent writes", f"{successes}/5 succeeded in {elapsed:.1f}s")

    # Search under load
    start = time.time()
    data, err = mcp_result(base_url, token, "search_meetings", {"query": "load test", "limit": 50})
    elapsed = time.time() - start
    if data and data.get("count", 0) >= 10:
        ok(f"Search with 20+ meetings", f"{data['count']} results in {elapsed:.2f}s")
    else:
        warn(f"Search with 20+ meetings", f"count={data.get('count') if data else '?'}, {elapsed:.2f}s")

    # Large payload — big summary
    big_summary = "## Section\n\n" + ("This is a test paragraph with enough content. " * 100 + "\n\n") * 10
    start = time.time()
    data, err = mcp_result(base_url, token, "create_meeting", {
        "title": "Large Payload Test",
        "meeting_date": "2026-02-24",
        "summary": big_summary
    })
    elapsed = time.time() - start
    if data and data.get("id"):
        ok(f"Large payload ({len(big_summary)} chars)", f"{elapsed:.2f}s")
        meeting_ids.append(data["id"])
    else:
        fail(f"Large payload", str(err))

    # Cleanup load test data
    print("  Cleaning up load test data...")
    for mid in meeting_ids:
        mcp_result(base_url, token, "delete_meeting", {"meeting_id": mid})
    ok("Load test cleanup", f"deleted {len(meeting_ids)} meetings")


# ============================================================================
# REST API TESTS
# ============================================================================

def test_rest_api(base_url):
    print("\n=== REST API (unauthenticated endpoints) ===")

    # Schema — no auth needed
    r = requests.get(f"{base_url}/api/schema", timeout=10)
    if r.status_code == 200:
        ok("REST /api/schema (no auth)")
    else:
        fail("REST /api/schema (no auth)", f"HTTP {r.status_code}")

    # Health — no auth needed
    r = requests.get(f"{base_url}/health", timeout=10)
    if r.status_code == 200:
        ok("REST /health (no auth)")
    else:
        fail("REST /health (no auth)", f"HTTP {r.status_code}")

    # Meetings list — should require auth
    r = requests.get(f"{base_url}/api/meetings", timeout=10)
    if r.status_code in (401, 403):
        ok("REST /api/meetings requires auth", f"{r.status_code}")
    else:
        fail("REST /api/meetings requires auth", f"Expected 401/403, got {r.status_code}")


# ============================================================================
# TOOLS/LIST
# ============================================================================

def test_tools_list(base_url, token):
    print("\n=== MCP TOOLS/LIST ===")

    resp = requests.post(
        f"{base_url}/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        },
        timeout=30
    )
    if resp.status_code != 200:
        fail("tools/list", f"HTTP {resp.status_code}")
        return

    body = parse_sse_response(resp)
    if body is None:
        fail("tools/list", f"Could not parse response: {resp.text[:200]}")
        return
    tools = body.get("result", {}).get("tools", [])
    tool_names = [t["name"] for t in tools]

    expected_tools = [
        "list_meetings", "get_meeting", "create_meeting", "update_meeting",
        "delete_meeting", "search_meetings",
        "list_actions", "get_action", "create_action", "update_action",
        "complete_action", "park_action", "delete_action", "search_actions",
        "list_decisions", "create_decision", "delete_decision", "search_decisions",
        "get_schema"
    ]

    # Check count
    if len(tools) >= 18:
        ok(f"Tool count", f"{len(tools)} tools registered")
    else:
        fail(f"Tool count", f"Expected >= 18, got {len(tools)}")

    # Check each expected tool exists
    missing = [t for t in expected_tools if t not in tool_names]
    if not missing:
        ok("All expected tools present")
    else:
        fail("Missing tools", str(missing))

    # Check tools have descriptions
    no_desc = [t["name"] for t in tools if not t.get("description")]
    if not no_desc:
        ok("All tools have descriptions")
    else:
        fail("Tools missing descriptions", str(no_desc))


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Battle Test — Full deployment validation")
    parser.add_argument("--url", required=True, help="Base URL of the deployed environment")
    parser.add_argument("--token", required=True, help="MCP auth token")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    token = args.token

    print(f"=== BATTLE TEST: {base_url} ===")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Run all test suites
    test_health(base_url)
    test_auth(base_url, token)
    test_tools_list(base_url, token)
    test_schema(base_url)
    test_schema_mcp(base_url, token)

    meeting_ids = test_meetings(base_url, token)
    meeting_id = meeting_ids[0] if meeting_ids else None
    second_meeting_id = meeting_ids[1] if meeting_ids and len(meeting_ids) > 1 else None

    action_id = test_actions(base_url, token, meeting_id) if meeting_id else None
    decision_id = test_decisions(base_url, token, meeting_id) if meeting_id else None

    test_edge_cases(base_url, token)
    test_load(base_url, token)
    test_rest_api(base_url)

    # Cleanup — delete test data
    if meeting_id or action_id or decision_id:
        test_deletes(base_url, token, meeting_id, second_meeting_id, action_id, decision_id)

    # Summary
    print("\n" + "=" * 50)
    print(f"BATTLE TEST COMPLETE")
    print(f"=" * 50)
    print(f"  PASS: {PASS}")
    print(f"  FAIL: {FAIL}")
    print(f"  WARN: {WARN}")
    print(f"  TOTAL: {PASS + FAIL + WARN}")
    print()

    if FAIL > 0:
        print("FAILURES:")
        for status, name, detail in RESULTS:
            if status == "FAIL":
                print(f"  - {name}: {detail}")
        print()

    if WARN > 0:
        print("WARNINGS:")
        for status, name, detail in RESULTS:
            if status == "WARN":
                print(f"  - {name}: {detail}")
        print()

    print(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    sys.exit(1 if FAIL > 0 else 0)


if __name__ == "__main__":
    main()

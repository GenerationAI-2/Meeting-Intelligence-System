# Session Stability Investigation — Action #1 (B2 Resurfaced)

**Date:** 2026-03-08
**Branch:** feature/action1-session-stability
**Original Fix:** A2 (Wave 1), commits ce057ee + c5d6d51, merged 23-24 Feb 2026

---

## Executive Summary

The session stability bug (401 errors after inactivity) has resurfaced despite A2's fix being present in the codebase. Investigation reveals that all three A2 changes are correctly implemented:
- API scope configured at login
- forceRefresh parameter on acquireTokenSilent
- 401 interceptor with retry logic

However, there is a **UX/flow issue**: when the refresh token is also expired, the code triggers `acquireTokenRedirect` but immediately returns `null`, causing the 401 interceptor to throw an error BEFORE the redirect completes. This leaves the user seeing a 401 error screen even though authentication recovery is in progress.

**Root cause hypothesis:** The redirect flow works but has a race condition where the error is displayed before the redirect completes, creating a poor user experience that appears as a "stuck 401" bug.

---

## Phase 1.2: Audit of A2 Changes

### What A2 Was Supposed to Fix

From the original A2 brief:
1. Add API scope to `loginRequest.scopes` (was empty `[]`)
2. Add `forceRefresh` parameter to `acquireTokenSilent`
3. Add 401 interceptor in `api.js` to trigger token refresh and retry

### Current State (Main Branch)

**✅ All three changes are present and correctly implemented:**

#### 1. authConfig.js (lines 21-27)
```javascript
// API scope — must be requested at login to establish a refresh token for the API resource.
// Without this, acquireTokenSilent has no refresh token and fails after the access token expires (~1hr).
const apiClientId = import.meta.env.VITE_API_CLIENT_ID || 'your-api-client-id';

export const loginRequest = {
    scopes: [`api://${apiClientId}/access_as_user`],
};
```
**Status:** ✅ Present. API scope is correctly configured.

#### 2. App.jsx (lines 23-46)
```javascript
const request = {
    scopes: [`api://${import.meta.env.VITE_API_CLIENT_ID}/access_as_user`],
    account: accounts[0],
    forceRefresh: options.forceRefresh || false,  // ← Line 28
};
try {
    const response = await instance.acquireTokenSilent(request);
    return response.accessToken;
} catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
        await instance.acquireTokenRedirect({
            scopes: [`api://${import.meta.env.VITE_API_CLIENT_ID}/access_as_user`],
            account: accounts[0],
        });
        return null;  // ← Problem: returns null immediately
    }
    console.warn("Silent token acquisition failed", error);
    return null;
}
```
**Status:** ✅ Present. forceRefresh parameter and redirect fallback are implemented.

**⚠️ Issue identified:** When `acquireTokenRedirect` is called (line 35-38), it initiates a browser redirect to Azure AD. This is asynchronous — the redirect happens after the function returns. But the code immediately returns `null` (line 39), which causes the 401 interceptor to fail.

#### 3. api.js (lines 50-70)
```javascript
// On 401, force a fresh token and retry once
if (response.status === 401 && !options._retried) {
    let freshToken = null;
    try {
        freshToken = await getAccessToken({ forceRefresh: true });
    } catch (e) {
        console.error("Failed to refresh token on 401", e);
    }
    if (freshToken) {  // ← If null (from redirect case), this is false
        headers['Authorization'] = `Bearer ${freshToken}`;
        const retryResponse = await fetch(url, {
            ...options,
            headers,
            _retried: true,
        });
        if (!retryResponse.ok) {
            throw new Error(`API error: ${retryResponse.status}`);
        }
        return retryResponse.json();
    }
}

if (!response.ok) {
    throw new Error(`API error: ${response.status}`);  // ← Throws before redirect completes
}
```
**Status:** ✅ Present. 401 interceptor with retry logic is implemented.

**⚠️ Flow issue:** When `getAccessToken({ forceRefresh: true })` triggers a redirect (because refresh token is expired), it returns `null`. The interceptor checks `if (freshToken)` which is false, so it falls through to line 72 and throws an error. The user sees this error BEFORE the redirect to Azure AD completes.

### Git History Confirmation

```bash
$ git log --oneline --grep="B2" --all
c5d6d51 fix: add 401 interceptor with token refresh fallback (B2)
ce057ee fix: configure MSAL scopes for silent token refresh (B2)
```

Both A2 commits are present in the main branch history. The fix was not reverted.

---

## Phase 1.4: MSAL Token Lifecycle

### MSAL Version
From `web/package.json`:
```json
"@azure/msal-browser": "^3.30.0",
"@azure/msal-react": "^2.2.0",
```

**MSAL v3.x uses refresh tokens stored in localStorage** — NOT iframe-based silent renewal. This is the correct modern approach.

### Expected Flow

1. **Login:**
   - User authenticates with Azure AD
   - MSAL requests scopes: `api://CLIENT_ID/access_as_user`
   - Azure AD returns:
     - Access token (expires ~1 hour)
     - Refresh token (expires ~24 hours, stored in localStorage)

2. **Access Token Expires:**
   - App calls `acquireTokenSilent({ forceRefresh: true })`
   - MSAL uses the refresh token to get a new access token from Azure AD
   - No user interaction required

3. **Refresh Token Also Expires:**
   - App calls `acquireTokenSilent`
   - MSAL throws `InteractionRequiredAuthError`
   - App calls `acquireTokenRedirect` → user is sent to Azure AD to re-authenticate

### Why the Bug Resurfaces

**Hypothesis:** The A2 fix handles scenarios 1 and 2 correctly, but scenario 3 (both tokens expired) has a UX race condition:

1. User is idle for >24 hours (refresh token expires)
2. User returns and clicks something → API call → 401
3. 401 interceptor calls `getAccessToken({ forceRefresh: true })`
4. `acquireTokenSilent` fails → `InteractionRequiredAuthError`
5. Code calls `acquireTokenRedirect` and returns `null`
6. Interceptor sees `null`, falls through, throws error
7. **User sees 401 error on screen**
8. A moment later, the redirect to Azure AD completes → user is taken to login page
9. User logs in, returns to app, everything works

**Result:** From the user's perspective, they see a brief 401 error flash before being redirected. If the error is caught by a page component and displayed persistently, the user might appear "stuck" on the error screen even though the redirect is happening.

---

## Phase 1.3: Infrastructure Config

### testing-instance Configuration

From `infra/parameters/testing-instance.bicepparam`:
```bicep
param minReplicas = 1
```

**Confirmed:** testing-instance is configured as always-on (minimum 1 replica). This rules out cold-start issues.

### Other Infrastructure Notes

- Container App: `mi-testing-instance`
- Resource Group: `meeting-intelligence-testing-instance-rg`
- Database: `mi-testing-instance` + `mi-testing-instance-control`
- 3 workspaces configured

No evidence of container restarts or scale-to-zero behavior that could contribute to the issue.

---

## Phase 1.1: Characterization

### Reproduction Notes

**User report:** "Users on the MI web interface hit 401 errors after a period of inactivity."

**Unable to reproduce remotely** without live browser session and intentional token expiry (would require >1 hour wait or manual token deletion from localStorage).

**Expected conditions for reproduction:**
1. User logs in successfully
2. User leaves the app open (or closes and returns) after access token expires (~1 hour)
3. Refresh token is also expired (~24 hours) OR not present in localStorage
4. User clicks any action that triggers an API call
5. 401 error appears before redirect to login

### What Should Happen

- Silent refresh works when access token expires but refresh token is valid
- Graceful redirect to login when both tokens are expired
- **No visible error to the user** — either it works silently or redirects immediately

### What Actually Happens (Hypothesis)

- Silent refresh likely works for the access-token-expired case
- **When both tokens are expired:** Error is thrown and displayed before the redirect completes
- User sees "API error: 401" message
- Then (after a delay) the browser redirects to Azure AD login
- **Perception:** User thinks the app is broken and manually refreshes or logs out

---

## Root Cause Analysis

### Primary Issue: Redirect Flow Returns Null

**In App.jsx, AuthenticationHandler:**

```javascript
if (error instanceof InteractionRequiredAuthError) {
    await instance.acquireTokenRedirect({
        scopes: [`api://${import.meta.env.VITE_API_CLIENT_ID}/access_as_user`],
        account: accounts[0],
    });
    return null;  // ← Returns immediately, before redirect completes
}
```

`acquireTokenRedirect` is **not awaitable for its completion** — it initiates a full-page navigation to Azure AD. The browser redirects away, so the promise resolves immediately (not when the user returns from login).

**In api.js, 401 interceptor:**

```javascript
if (freshToken) {
    // retry the request
}
// If freshToken is null, fall through to:
if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
}
```

Since `freshToken` is `null` (from the redirect case), the code throws an error. **This error is thrown before the redirect takes the user away from the page.**

### Why This Wasn't Caught in A2

The A2 brief noted: "needs ~1hr live verification" — it's unclear whether that verification ever happened. The fix likely works for the **access token refresh** case (which can be verified quickly), but the **both tokens expired** case requires 24+ hours of inactivity or manual localStorage manipulation to test.

---

## Recommended Fix Approach

### Option A: Don't Throw Error on Redirect Path (Preferred)

When `getAccessToken` returns `null` AND we're in a redirect scenario, don't throw an error. Instead, return a response or show a loading state, because the redirect is already in progress.

**Implementation:**
1. In `api.js`, check if the 401 response triggers a redirect
2. If yes, don't throw — either return a special "redirect in progress" response or let the page show a loading spinner
3. The redirect will take the user to Azure AD, they'll log in, and come back

**Pros:** Fixes the UX issue without changing MSAL behavior
**Cons:** Requires differentiating between "token refresh failed" and "redirect initiated"

### Option B: Catch Redirect Case in App.jsx

Instead of returning `null` when `InteractionRequiredAuthError` is thrown, handle it specially:

```javascript
if (error instanceof InteractionRequiredAuthError) {
    // Don't just redirect and return null — track that a redirect is happening
    await instance.acquireTokenRedirect({...});
    // This line never executes because redirect navigates away
}
```

Pair this with a global MSAL event listener that detects when a redirect is in progress and shows a loading overlay instead of letting errors bubble up.

**Pros:** More robust, handles redirect state explicitly
**Cons:** More complex, requires MSAL event handling

### Option C: Improve Error UX

Keep the current flow but improve how errors are displayed to the user:
- Catch 401 errors in the UI layer
- Show a message like "Your session has expired. Redirecting to login..." instead of "API error: 401"
- The redirect will happen after the message is shown

**Pros:** Minimal code change
**Cons:** Still shows an error message, doesn't fully solve the "stuck" perception

---

## Recommendation

**Option A** is the best balance of correctness and UX improvement. The fix should:

1. **In `api.js`, 401 interceptor:**
   - When `getAccessToken({ forceRefresh: true })` returns `null`, check if a redirect is in progress (MSAL provides `inProgress` status)
   - If redirect is happening, **don't throw an error** — instead, return early or show a loading state
   - The page will be navigated away anyway, so throwing an error just creates a bad UX flash

2. **In `App.jsx`, AuthenticationHandler:**
   - Consider wrapping the redirect in a try-catch and setting a flag that a redirect is in progress
   - Or use MSAL's `inProgress` state to detect redirect status

3. **Test thoroughly:**
   - Access token expired, refresh token valid → silent refresh works
   - Both tokens expired → redirect happens without showing error
   - Network error → appropriate error is shown

---

## Next Steps

1. **Report findings to Caleb** for review and approval of fix approach
2. **Implement Option A** (or alternative if Caleb prefers)
3. **Test on testing-instance** with manual localStorage manipulation to simulate expired tokens
4. **Verify with Sam onboarding scenario** — new user experience should be seamless

---

## Files to Modify (Pending Approval)

Based on Option A:
- `web/src/services/api.js` — 401 interceptor logic
- `web/src/App.jsx` — AuthenticationHandler redirect handling (possibly)
- `web/src/authConfig.js` — No changes expected

---

**Investigation Status:** COMPLETE
**Awaiting:** Caleb's approval to proceed with fix implementation

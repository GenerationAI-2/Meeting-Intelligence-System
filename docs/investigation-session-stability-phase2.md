# Session Stability Investigation — Phase 2 (Code Analysis)

**Date:** 2026-03-08
**Branch:** feature/action1-session-stability
**Diagnostic Logging Commit:** b4b94e1

---

## Critical Bugs Identified (Without Live Testing)

Based on code analysis and the real-world behavior (401 persists after hard refresh, no redirect ever fires), I've identified **two critical bugs** in `App.jsx`:

### Bug #1: accounts.length === 0 Silently Returns Null

**Location:** `web/src/App.jsx` line 24-45 (before diagnostic logging)

**Original code:**
```javascript
if (accounts.length > 0) {
    // try to get token
}
return null;  // Line 45 - silent failure if no accounts
```

**Problem:**
- On hard refresh, MSAL re-initializes from localStorage
- If the cached account is expired/stale, MSAL might not load it into the `accounts` array
- If `accounts` is empty, the function immediately returns `null` with no attempt to redirect
- This means **any API call when accounts.length === 0 will get a null token and fail with 401**

**Why this causes the stuck-on-401 bug:**
1. User's tokens expire
2. Hard refresh → MSAL loads from localStorage
3. Cached account is stale/expired → `accounts.length === 0`
4. API call → `getAccessToken()` returns `null`
5. Request gets 401
6. 401 interceptor calls `getAccessToken({ forceRefresh: true })` → still returns `null` (no accounts)
7. Can't retry, throws error
8. User stuck on 401, no redirect

**Expected behavior:**
If no accounts are found, the app should redirect to login, not silently return null.

### Bug #2: Generic Catch Block Swallows Non-InteractionRequiredAuthError

**Location:** `web/src/App.jsx` lines 41-42 (before diagnostic logging)

**Original code:**
```javascript
catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
        await instance.acquireTokenRedirect({...});
        return null;
    }
    console.warn("Silent token acquisition failed", error);  // Generic catch
    return null;  // No redirect for other error types!
}
```

**Problem:**
- The ONLY error type that triggers a redirect is `InteractionRequiredAuthError`
- But `acquireTokenSilent` can throw many other error types:
  - `BrowserAuthError` - e.g., "no_tokens_found", "interaction_in_progress", "no_account_error"
  - `ClientAuthError` - configuration issues
  - `ServerError` - Azure AD errors
  - Generic `Error` - unexpected failures
- If ANY non-InteractionRequiredAuthError is thrown, the code just logs a warning and returns `null`
- **No redirect happens**

**Why this causes the stuck-on-401 bug:**
When tokens are expired and `acquireTokenSilent` is called:
1. MSAL tries to use the refresh token
2. If refresh token is also expired OR not present, MSAL throws an error
3. **The error type thrown may NOT be `InteractionRequiredAuthError`**
4. Common scenario: MSAL throws `BrowserAuthError` with message like "cached_token_expired" or "no_tokens_found"
5. Generic catch block swallows it, returns `null`
6. 401 interceptor gets `null`, can't retry, throws error
7. User stuck on 401, no redirect

**Expected behavior:**
ANY token acquisition failure should either succeed (return a valid token) or redirect to login. Never silently return null.

---

## Why Hard Refresh Doesn't Help

**The cycle:**
1. Browser reloads page
2. MSAL re-initializes from localStorage
3. Cached tokens (even if expired) are still in localStorage
4. One of two things happens:
   - **Scenario A:** MSAL loads expired account → `accounts.length > 0` but tokens are stale → `acquireTokenSilent` fails with non-InteractionRequiredAuthError → Bug #2 → returns null
   - **Scenario B:** MSAL doesn't load expired account → `accounts.length === 0` → Bug #1 → returns null immediately
5. API call → 401
6. Repeat

**The cache is the problem.** Expired/stale tokens remain in localStorage. MSAL keeps trying to use them. The error handling doesn't trigger a redirect.

---

## Why Manual Logout Works

**The user's workaround:**
1. Click logout → MSAL calls `instance.logoutRedirect()` or similar
2. This clears ALL MSAL cache from localStorage
3. Press back → returns to app
4. `accounts.length === 0` AND `useIsAuthenticated()` returns false
5. `ProtectedRoute` component (lines 52-69) sees user is not authenticated
6. Redirects to `/login` (line 65)
7. User logs in, fresh tokens issued, everything works

**Key insight:** Logout clears the cache, which breaks the cycle. The fix must do the same thing automatically.

---

## Root Cause: Error Type Mismatch

**Hypothesis:**
When tokens are expired, `acquireTokenSilent` throws `BrowserAuthError` or `ClientAuthError`, NOT `InteractionRequiredAuthError`.

**Why InteractionRequiredAuthError might not be thrown:**
- `InteractionRequiredAuthError` is typically thrown when Azure AD requires user interaction (e.g., MFA, consent)
- But when tokens are simply expired and refresh fails, MSAL might throw `BrowserAuthError` instead
- Example MSAL error codes that throw `BrowserAuthError`:
  - `no_tokens_found` - no cached tokens
  - `no_account_error` - no account in cache
  - `token_renewal_error` - refresh token renewal failed
  - `user_cancelled` - user cancelled interaction

**MSAL documentation** indicates that `InteractionRequiredAuthError` is a specific subclass. Other auth errors (cache issues, network failures, etc.) throw different error types. The current code ONLY handles `InteractionRequiredAuthError`, so all other failures are swallowed.

---

## Recommended Fix: Fail-Safe Token Acquisition

**Principle:** Never return null silently. Either get a valid token or redirect to login.

### Fix for Bug #1: Check accounts.length and redirect if empty

```javascript
if (accounts.length === 0) {
    console.error("[AUTH] No accounts found - redirecting to login");
    // Clear any stale cache
    await instance.clearCache();
    await instance.loginRedirect({
        scopes: [`api://${import.meta.env.VITE_API_CLIENT_ID}/access_as_user`]
    });
    return null; // Code never reaches here - redirect navigates away
}
```

### Fix for Bug #2: Redirect on ANY token acquisition failure

```javascript
catch (error) {
    console.error("[AUTH] Token acquisition failed - clearing cache and redirecting to login", error);
    // Don't check error type - ANY failure means we need to re-authenticate
    await instance.clearCache();
    await instance.loginRedirect({
        scopes: [`api://${import.meta.env.VITE_API_CLIENT_ID}/access_as_user`]
    });
    return null; // Code never reaches here - redirect navigates away
}
```

**Rationale:**
- If `acquireTokenSilent` fails for ANY reason, the user needs to re-authenticate
- Checking for specific error types is fragile - MSAL's error types might change, or unexpected errors might occur
- The fail-safe approach: clear cache + redirect to login
- This mirrors what the user does manually (logout + login)

**Why clearCache is critical:**
- Just calling `loginRedirect` might not clear stale tokens from cache
- On return from login, stale cache could cause the same issue again
- `clearCache()` ensures a clean slate

### Alternative: More Granular Error Handling

If we want to preserve the "silent refresh" behavior when it's genuinely possible:

```javascript
catch (error) {
    console.error("[AUTH] Token acquisition failed", error);

    // Only redirect if it's a real auth failure
    // Allow transient network errors to fail without redirecting
    const shouldRedirect = (
        error instanceof InteractionRequiredAuthError ||
        error.name === 'BrowserAuthError' ||
        error.name === 'ClientAuthError' ||
        error.errorCode === 'no_tokens_found' ||
        error.errorCode === 'no_account_error' ||
        error.errorCode === 'token_renewal_error'
    );

    if (shouldRedirect) {
        await instance.clearCache();
        await instance.loginRedirect({
            scopes: [`api://${import.meta.env.VITE_API_CLIENT_ID}/access_as_user`]
        });
    }

    return null;
}
```

**I recommend the simpler approach (redirect on ANY failure).** The more granular approach adds complexity and might still miss edge cases.

---

## Testing Strategy (After Fix)

### Local Testing
1. Build and run locally
2. Log in successfully
3. Open browser DevTools → Application → Local Storage
4. Delete MSAL tokens from localStorage (or set them to expired values)
5. Trigger an API call (e.g., navigate to /meetings)
6. Expected: Redirect to login, NOT stuck on 401

### Testing-Instance Testing
1. Deploy the fix to testing-instance
2. Log in, use the app
3. Wait ~1 hour for tokens to expire (or manually delete from localStorage)
4. Trigger an API call
5. Expected: Either silent refresh works OR redirect to login occurs
6. Hard refresh → should still recover gracefully

### Sam Onboarding Scenario
1. New user logs in
2. Uses app for a while
3. Leaves it idle overnight
4. Returns next day
5. Expected: Seamless re-authentication (redirect to login, log back in, continue working)
6. Should NOT see 401 error at any point

---

## Next Steps

1. **Implement the fix** (both Bug #1 and Bug #2)
2. **Test locally** to verify redirect behavior
3. **Deploy to testing-instance** for integration testing
4. **Verify with Sam onboarding scenario**
5. **Update CLAUDE.md** with learnings about MSAL error handling

---

## Questions for Caleb

Before implementing the fix, please confirm:

1. **Approach:** Should I use the simple "redirect on ANY failure" approach, or the more granular error-type checking?
2. **clearCache:** Should we clear MSAL cache before redirecting, or let the login flow handle it?
3. **Testing:** Can you deploy the diagnostic build (commit b4b94e1) to testing-instance and share the console logs when the 401 occurs? This would confirm the exact error type being thrown.
4. **Alternative:** Should I implement the fix immediately based on this analysis, or wait for live browser confirmation first?

**My recommendation:** Implement the simple fix now (redirect on ANY failure + clearCache), test locally, then deploy to testing-instance for verification. The diagnostic logging is already in place, so if the fix doesn't work, we'll get detailed logs showing why.

---

**Status:** Ready to implement fix pending approval

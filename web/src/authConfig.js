/**
 * MSAL Configuration
 * Configure these values from your Azure Entra ID app registration
 */

export const msalConfig = {
    auth: {
        // Replace with your Azure AD app registration client ID
        clientId: import.meta.env.VITE_SPA_CLIENT_ID || 'your-spa-client-id',
        // Replace with your tenant ID
        authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID || 'your-tenant-id'}`,
        redirectUri: window.location.origin,
        postLogoutRedirectUri: window.location.origin,
    },
    cache: {
        cacheLocation: 'localStorage',
        storeAuthStateInCookie: false,
    },
};

// API scope — must be requested at login to establish a refresh token for the API resource.
// Without this, acquireTokenSilent has no refresh token and fails after the access token expires (~1hr).
const apiClientId = import.meta.env.VITE_API_CLIENT_ID || 'your-api-client-id';

export const loginRequest = {
    scopes: [`api://${apiClientId}/access_as_user`],
};

export const apiConfig = {
    baseUrl: import.meta.env.VITE_API_URL || '/api',
};

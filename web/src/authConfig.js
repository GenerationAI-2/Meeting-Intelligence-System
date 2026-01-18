/**
 * MSAL Configuration
 * Configure these values from your Azure Entra ID app registration
 */

export const msalConfig = {
    auth: {
        // Replace with your Azure AD app registration client ID
        clientId: import.meta.env.VITE_AZURE_CLIENT_ID || 'your-client-id',
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

export const loginRequest = {
    scopes: ['User.Read'],
};

export const apiConfig = {
    baseUrl: import.meta.env.VITE_API_URL || '/api',
};

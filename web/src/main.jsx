import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { PublicClientApplication } from '@azure/msal-browser';
import { MsalProvider } from '@azure/msal-react';
import App from './App';
import { msalConfig } from './authConfig';
import './index.css';

const msalInstance = new PublicClientApplication(msalConfig);

// MSAL v3 requires asynchronous initialization
msalInstance.initialize().then(async () => {
    // Handle redirect result
    const response = await msalInstance.handleRedirectPromise().catch(err => console.error(err));

    // Set active account if login was successful or if account exists in cache
    if (response?.account) {
        msalInstance.setActiveAccount(response.account);
    } else {
        const accounts = msalInstance.getAllAccounts();
        if (accounts.length > 0) {
            msalInstance.setActiveAccount(accounts[0]);
        }
    }

    ReactDOM.createRoot(document.getElementById('root')).render(
        <React.StrictMode>
            <MsalProvider instance={msalInstance}>
                <BrowserRouter>
                    <App />
                </BrowserRouter>
            </MsalProvider>
        </React.StrictMode>
    );
});

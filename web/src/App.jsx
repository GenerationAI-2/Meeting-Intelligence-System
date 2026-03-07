import { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useIsAuthenticated, useMsal } from '@azure/msal-react';
import { InteractionRequiredAuthError, InteractionStatus } from '@azure/msal-browser';
import Layout from './components/Layout';
import MeetingsList from './pages/MeetingsList';
import MeetingDetail from './pages/MeetingDetail';
import ActionsList from './pages/ActionsList';
import ActionDetail from './pages/ActionDetail';
import DecisionsList from './pages/DecisionsList';
import DecisionDetail from './pages/DecisionDetail';
import WorkspaceAdmin from './pages/WorkspaceAdmin';
import Settings from './pages/Settings';
import Login from './pages/Login';
import { setAccessTokenProvider } from './services/api';
import { WorkspaceProvider } from './contexts/WorkspaceContext';

// Component to handle token acquisition and injection into API service
function AuthenticationHandler({ children }) {
    const { instance, accounts } = useMsal();

    useEffect(() => {
        setAccessTokenProvider(async (options = {}) => {
            // Fix Bug #1: No accounts cached (e.g., after hard refresh with expired tokens)
            // Clear cache and redirect to login instead of silently returning null
            if (accounts.length === 0) {
                console.error("[AUTH] No accounts found - clearing cache and redirecting to login");
                await instance.clearCache();
                await instance.loginRedirect({
                    scopes: [`api://${import.meta.env.VITE_API_CLIENT_ID}/access_as_user`]
                });
                // Redirect navigates away, code never returns
                return null;
            }

            const request = {
                scopes: [`api://${import.meta.env.VITE_API_CLIENT_ID}/access_as_user`],
                account: accounts[0],
                forceRefresh: options.forceRefresh || false,
            };

            try {
                const response = await instance.acquireTokenSilent(request);
                return response.accessToken;
            } catch (error) {
                // Fix Bug #2: ANY token acquisition failure triggers redirect
                // Don't check error type - fragile and misses edge cases (BrowserAuthError, etc.)
                // Clear stale cache to ensure clean re-authentication
                console.error("[AUTH] Token acquisition failed - clearing cache and redirecting to login", {
                    errorType: error.constructor.name,
                    errorMessage: error.message
                });
                await instance.clearCache();
                await instance.loginRedirect({
                    scopes: [`api://${import.meta.env.VITE_API_CLIENT_ID}/access_as_user`]
                });
                // Redirect navigates away, code never returns
                return null;
            }
        });
    }, [instance, accounts]);

    return children;
}

function ProtectedRoute({ children }) {
    const isAuthenticated = useIsAuthenticated();
    const { inProgress } = useMsal();

    if (inProgress !== InteractionStatus.None) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-600"></div>
            </div>
        );
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    return children;
}

function App() {
    return (
        <AuthenticationHandler>
            <Routes>
                <Route path="/login" element={<Login />} />
                <Route
                    path="/*"
                    element={
                        <ProtectedRoute>
                            <WorkspaceProvider>
                                <Layout>
                                    <Routes>
                                        <Route path="/" element={<Navigate to="/meetings" replace />} />
                                        <Route path="/meetings" element={<MeetingsList />} />
                                        <Route path="/meetings/:id" element={<MeetingDetail />} />
                                        <Route path="/actions" element={<ActionsList />} />
                                        <Route path="/actions/:id" element={<ActionDetail />} />
                                        <Route path="/decisions" element={<DecisionsList />} />
                                        <Route path="/decisions/:id" element={<DecisionDetail />} />
                                        <Route path="/admin/workspaces" element={<WorkspaceAdmin />} />
                                        <Route path="/settings" element={<Settings />} />
                                    </Routes>
                                </Layout>
                            </WorkspaceProvider>
                        </ProtectedRoute>
                    }
                />
            </Routes>
        </AuthenticationHandler>
    );
}

export default App;

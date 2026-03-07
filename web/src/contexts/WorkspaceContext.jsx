import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { workspaceApi, setCurrentWorkspaceId, AccessDeniedError } from '../services/api';

const WorkspaceContext = createContext(null);

const STORAGE_KEY = 'mi_workspace_id';

export function WorkspaceProvider({ children }) {
    const [workspaces, setWorkspaces] = useState([]);
    const [activeWorkspace, setActiveWorkspace] = useState(null);
    const [permissions, setPermissions] = useState({ can_write: false, is_chair_or_admin: false });
    const [isOrgAdmin, setIsOrgAdmin] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [workspaceVersion, setWorkspaceVersion] = useState(0);

    const fetchMe = useCallback(async (workspaceId = null) => {
        try {
            // Set header before fetching so /api/me resolves the right workspace
            if (workspaceId) {
                setCurrentWorkspaceId(workspaceId);
            }
            const data = await workspaceApi.me();
            setWorkspaces(data.workspaces || []);
            setActiveWorkspace(data.active_workspace || null);
            setPermissions(data.permissions || { can_write: false, is_chair_or_admin: false });
            setIsOrgAdmin(data.is_org_admin || false);
            setError(null);

            // Persist the active workspace ID
            if (data.active_workspace?.id) {
                localStorage.setItem(STORAGE_KEY, String(data.active_workspace.id));
                setCurrentWorkspaceId(data.active_workspace.id);
            }
        } catch (err) {
            console.error('Failed to fetch workspace context:', err);

            // Handle 403 (access denied) specifically
            if (err instanceof AccessDeniedError) {
                console.log('[WORKSPACE] Access denied to current workspace - checking available workspaces');

                // Clear the workspace header and try to fetch available workspaces
                setCurrentWorkspaceId(null);
                localStorage.removeItem(STORAGE_KEY);

                try {
                    // Fetch workspace list without a specific workspace ID
                    const data = await workspaceApi.me();

                    if (data.workspaces && data.workspaces.length > 0) {
                        // User has other workspaces - switch to the first one
                        console.log(`[WORKSPACE] Switching to available workspace: ${data.workspaces[0].name}`);
                        setError('Your access to the previous workspace was revoked. Switched to an available workspace.');

                        // Switch to first available workspace
                        const newWorkspaceId = data.workspaces[0].id;
                        localStorage.setItem(STORAGE_KEY, String(newWorkspaceId));
                        setCurrentWorkspaceId(newWorkspaceId);

                        // Fetch again with the new workspace to get permissions
                        const updatedData = await workspaceApi.me();
                        setWorkspaces(updatedData.workspaces || []);
                        setActiveWorkspace(updatedData.active_workspace || null);
                        setPermissions(updatedData.permissions || { can_write: false, is_chair_or_admin: false });
                        setIsOrgAdmin(updatedData.is_org_admin || false);
                    } else {
                        // User has no workspaces - complete access revocation
                        console.error('[WORKSPACE] User has no workspace access');
                        setError('Your workspace access has been revoked. Please contact your administrator.');
                        setWorkspaces([]);
                        setActiveWorkspace(null);
                        setPermissions({ can_write: false, is_chair_or_admin: false });
                        setIsOrgAdmin(false);
                    }
                } catch (retryErr) {
                    console.error('[WORKSPACE] Failed to fetch available workspaces after 403:', retryErr);
                    setError('Unable to load workspace information. Your access may have been revoked.');
                    setCurrentWorkspaceId(null);
                }
            } else {
                // Other errors (network, etc.)
                setError(err.message);
                // If workspace fetch fails, clear workspace header so requests still work
                setCurrentWorkspaceId(null);
            }
        } finally {
            setLoading(false);
        }
    }, []);

    // Initial load — restore saved workspace
    useEffect(() => {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            setCurrentWorkspaceId(saved);
        }
        fetchMe(saved || null);
    }, [fetchMe]);

    const switchWorkspace = useCallback(async (workspaceId) => {
        setLoading(true);
        localStorage.setItem(STORAGE_KEY, String(workspaceId));
        await fetchMe(workspaceId);
        setWorkspaceVersion(prev => prev + 1);
    }, [fetchMe]);

    const refreshWorkspaces = useCallback(async () => {
        const saved = localStorage.getItem(STORAGE_KEY);
        await fetchMe(saved || null);
    }, [fetchMe]);

    const value = {
        workspaces,
        activeWorkspace,
        permissions,
        isOrgAdmin,
        loading,
        error,
        switchWorkspace,
        refreshWorkspaces,
        workspaceVersion,
    };

    return (
        <WorkspaceContext.Provider value={value}>
            {children}
        </WorkspaceContext.Provider>
    );
}

export function useWorkspace() {
    const ctx = useContext(WorkspaceContext);
    if (!ctx) {
        // Return safe defaults when outside provider (e.g., login page)
        return {
            workspaces: [],
            activeWorkspace: null,
            permissions: { can_write: true, is_chair_or_admin: false },
            isOrgAdmin: false,
            loading: false,
            error: null,
            switchWorkspace: () => {},
            refreshWorkspaces: () => {},
            workspaceVersion: 0,
        };
    }
    return ctx;
}

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { workspaceApi, setCurrentWorkspaceId } from '../services/api';

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
            setError(err.message);
            // If workspace fetch fails, clear workspace header so requests still work
            setCurrentWorkspaceId(null);
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

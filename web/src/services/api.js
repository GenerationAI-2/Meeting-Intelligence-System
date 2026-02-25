import { apiConfig } from '../authConfig';

/**
 * API service for meeting intelligence data
 */

// Token provider to avoid circular dependencies with React hooks
let getAccessToken = async () => null;

export const setAccessTokenProvider = (provider) => {
    getAccessToken = provider;
};

// Workspace ID provider — set by WorkspaceContext on switch
let currentWorkspaceId = null;

export const setCurrentWorkspaceId = (id) => {
    currentWorkspaceId = id;
};

async function fetchApi(endpoint, options = {}) {
    const url = `${apiConfig.baseUrl}${endpoint}`;

    // Get token if available
    let token = null;
    try {
        token = await getAccessToken();
    } catch (e) {
        console.error("Failed to acquire token", e);
    }

    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    if (currentWorkspaceId) {
        headers['X-Workspace-ID'] = String(currentWorkspaceId);
    }

    const response = await fetch(url, {
        ...options,
        headers,
    });

    // On 401, force a fresh token and retry once
    if (response.status === 401 && !options._retried) {
        let freshToken = null;
        try {
            freshToken = await getAccessToken({ forceRefresh: true });
        } catch (e) {
            console.error("Failed to refresh token on 401", e);
        }
        if (freshToken) {
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
        throw new Error(`API error: ${response.status}`);
    }

    return response.json();
}

// Meetings API
export const meetingsApi = {
    list: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchApi(`/meetings${query ? `?${query}` : ''}`);
    },

    get: (id) => fetchApi(`/meetings/${id}`),

    search: (query, limit = 10) =>
        fetchApi(`/meetings/search?query=${encodeURIComponent(query)}&limit=${limit}`),

    delete: (id) => fetchApi(`/meetings/${id}`, { method: 'DELETE' }),
};

// Actions API
export const actionsApi = {
    list: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchApi(`/actions${query ? `?${query}` : ''}`);
    },

    get: (id) => fetchApi(`/actions/${id}`),

    updateStatus: (id, status) =>
        fetchApi(`/actions/${id}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status }),
        }),

    owners: () => fetchApi('/actions/owners'),

    delete: (id) => fetchApi(`/actions/${id}`, { method: 'DELETE' }),
};

// Decisions API
export const decisionsApi = {
    list: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchApi(`/decisions${query ? `?${query}` : ''}`);
    },

    get: (id) => fetchApi(`/decisions/${id}`),

    delete: (id) => fetchApi(`/decisions/${id}`, { method: 'DELETE' }),
};

// Workspace API
export const workspaceApi = {
    me: () => fetchApi('/me'),

    // Admin endpoints
    listWorkspaces: () => fetchApi('/admin/workspaces'),

    createWorkspace: (data) =>
        fetchApi('/admin/workspaces', {
            method: 'POST',
            body: JSON.stringify(data),
        }),

    archiveWorkspace: (id, isArchived) =>
        fetchApi(`/admin/workspaces/${id}`, {
            method: 'PATCH',
            body: JSON.stringify({ is_archived: isArchived }),
        }),

    listMembers: (wsId) => fetchApi(`/admin/workspaces/${wsId}/members`),

    addMember: (wsId, data) =>
        fetchApi(`/admin/workspaces/${wsId}/members`, {
            method: 'POST',
            body: JSON.stringify(data),
        }),

    updateMemberRole: (wsId, userId, role) =>
        fetchApi(`/admin/workspaces/${wsId}/members/${userId}`, {
            method: 'PATCH',
            body: JSON.stringify({ role }),
        }),

    removeMember: (wsId, userId) =>
        fetchApi(`/admin/workspaces/${wsId}/members/${userId}`, {
            method: 'DELETE',
        }),
};

import { apiConfig } from '../authConfig';

/**
 * API service for meeting intelligence data
 */

// Token provider to avoid circular dependencies with React hooks
let getAccessToken = async () => null;

export const setAccessTokenProvider = (provider) => {
    getAccessToken = provider;
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

    const response = await fetch(url, {
        ...options,
        headers,
    });

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
};

// Decisions API
export const decisionsApi = {
    list: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchApi(`/decisions${query ? `?${query}` : ''}`);
    },

    get: (id) => fetchApi(`/decisions/${id}`),
};

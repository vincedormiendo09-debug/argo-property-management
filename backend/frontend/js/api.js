// backend/frontend/js/api.js

const API_BASE = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1')
    ? 'http://127.0.0.1:8000/api'
    : '/api';

function getSession() {
    try {
        const session = JSON.parse(localStorage.getItem('argo_session') || '{}');
        const token = session.token || localStorage.getItem('token') || localStorage.getItem('argo_token') || null;
        const user = session.user || JSON.parse(localStorage.getItem('argo_user') || '{}');
        const role = localStorage.getItem('argo_pov') || localStorage.getItem('user_role') || session.role || null;
        const orgId = localStorage.getItem('organization_id') || session.organization_id || 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';

        if (!token && !role) return null;

        return {
            token,
            user,
            role,
            organization_id: orgId
        };
    } catch {
        return null;
    }
}

async function apiRequest(endpoint, options = {}) {
    const session = getSession();
    const token = session?.token || localStorage.getItem('token') || localStorage.getItem('argo_token');
    
    // Normalize endpoint path to avoid double slashes
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${API_BASE}${cleanEndpoint}`;

    // Configure headers (Omit Content-Type for FormData uploads so browser sets boundary)
    const isFormData = options.body instanceof FormData;
    const headers = {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        ...options.headers
    };

    try {
        const response = await fetch(url, { ...options, headers });

        if (response.status === 401) {
            localStorage.clear();
            sessionStorage.clear();
            window.location.replace('index.html');
            return null;
        }

        if (response.status === 204) {
            return { success: true };
        }

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: `Request failed with status ${response.status}` }));
            throw new Error(err.detail || JSON.stringify(err));
        }

        return await response.json();
    } catch (error) {
        console.error(`[API Error] ${options.method || 'GET'} ${cleanEndpoint}:`, error.message);
        throw error;
    }
}

// Convenience CRUD HTTP Helper Methods
const api = {
    get: (endpoint, options = {}) => apiRequest(endpoint, { method: 'GET', ...options }),
    
    post: (endpoint, data, options = {}) => {
        const isFormData = data instanceof FormData;
        return apiRequest(endpoint, {
            method: 'POST',
            body: isFormData ? data : JSON.stringify(data),
            ...options
        });
    },

    put: (endpoint, data, options = {}) => {
        const isFormData = data instanceof FormData;
        return apiRequest(endpoint, {
            method: 'PUT',
            body: isFormData ? data : JSON.stringify(data),
            ...options
        });
    },

    delete: (endpoint, options = {}) => apiRequest(endpoint, { method: 'DELETE', ...options })
};

// Global Exports
window.API_BASE = API_BASE;
window.getSession = getSession;
window.apiRequest = apiRequest;
window.api = api;
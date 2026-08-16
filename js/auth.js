/**
 * ARGO Property Management - Strict Navigation Guard & Session Security
 */
(function enforceRoleGuard() {
    // 1. Extract and sanitize current HTML filename (strips out query params ? and hashes #)
    const rawFilename = window.location.pathname.split('/').pop() || 'index.html';
    const currentPath = rawFilename.split('?')[0].split('#')[0].toLowerCase();

    // Shared public pages accessible without login
    const SHARED_PUBLIC_PAGES = ['index.html', 'login.html', 'register.html', ''];
    if (SHARED_PUBLIC_PAGES.includes(currentPath)) {
        return;
    }

    // 2. Retrieve session variables with fallbacks & normalize role aliases
    const rawRole = (
        localStorage.getItem('argo_pov') || 
        localStorage.getItem('user_role') || 
        localStorage.getItem('role') || 
        ''
    ).toLowerCase().trim();

    const token = localStorage.getItem('token') || localStorage.getItem('argo_token');
    const orgId = localStorage.getItem('organization_id') || 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';

    // Normalize roles
    let userRole = '';
    if (['client', 'tenant', 'client_pov'].includes(rawRole)) {
        userRole = 'client';
    } else if (['owner', 'property_owner', 'investor'].includes(rawRole)) {
        userRole = 'owner';
    } else if (['admin', 'pm', 'property_manager'].includes(rawRole)) {
        userRole = 'admin';
    }

    // 3. Unauthenticated Guard
    if (!userRole || !orgId) {
        alert('🔒 Session Expired or Unauthenticated: Please sign in first.');
        window.location.replace('index.html');
        return;
    }

    // 4. SHARED AUTHENTICATED PAGES (Immediately grants access to all logged-in roles)
    const SHARED_AUTHENTICATED_PAGES = [
        'notification.html', 
        'account.html', 
        'logout.html', 
        'inspections.html',
        'property-ownership.html',
        'transaction.html'
    ];

    if (SHARED_AUTHENTICATED_PAGES.includes(currentPath)) {
        return; // Early return bypasses role-specific checks completely
    }

    // 5. Role-Specific Whitelists
    const roleRoutes = {
        admin: [
            'dashboard.html', 'properties.html', 'buildings.html', 'units.html',
            'tenants.html', 'owners.html', 'leases.html', 'invoices.html',
            'rent-collection.html', 'utilities.html', 'meter-readings.html',
            'maintenance.html', 'documents.html', 'reports.html', 'settings.html',
            'move-in-checklist.html', 'move-out-settlement.html'
        ],
        owner: [
            'owner-dashboard.html', 'owner-properties.html', 'owner-financials.html',
            'owner-reports.html', 'owner-statements.html', 'owner-documents.html'
        ],
        client: [
            'client-dashboard.html', 'client-billing.html', 'client-utilities.html',
            'client-maintenance.html', 'client-documents.html'
        ]
    };

    // 6. Role Authorization Check
    let isAuthorized = false;

    if (userRole === 'client') {
        isAuthorized = currentPath.startsWith('client-') || roleRoutes.client.includes(currentPath);
    } else if (userRole === 'owner') {
        isAuthorized = currentPath.startsWith('owner-') || roleRoutes.owner.includes(currentPath);
    } else if (userRole === 'admin') {
        isAuthorized = !currentPath.startsWith('client-') && 
                      !currentPath.startsWith('owner-') && 
                      (roleRoutes.admin.includes(currentPath) || !currentPath.includes('-'));
    }

    if (!isAuthorized) {
        alert(`🚫 Access Denied!\n\nYour account role (${userRole.toUpperCase()}) is not authorized to access '${currentPath}'.\n\nRedirecting to your workspace...`);

        if (userRole === 'admin') {
            window.location.replace('dashboard.html');
        } else if (userRole === 'owner') {
            window.location.replace('owner-dashboard.html');
        } else if (userRole === 'client') {
            window.location.replace('client-dashboard.html');
        } else {
            window.location.replace('index.html');
        }
    }
})();

/**
 * Global Authentication & API Header Helpers
 */
function getAuthToken() {
    return localStorage.getItem('token') || localStorage.getItem('argo_token') || '';
}

function getAuthHeaders() {
    const token = getAuthToken();
    return {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    };
}

function getCurrentUser() {
    try {
        return JSON.parse(localStorage.getItem('argo_user') || '{}');
    } catch (e) {
        return {};
    }
}

function getNormalizedRole() {
    const rawRole = (
        localStorage.getItem('argo_pov') || 
        localStorage.getItem('user_role') || 
        localStorage.getItem('role') || 
        'admin'
    ).toLowerCase().trim();

    if (['client', 'tenant', 'client_pov'].includes(rawRole)) return 'client';
    if (['owner', 'property_owner', 'investor'].includes(rawRole)) return 'owner';
    return 'admin';
}

/**
 * Global Logout Helper with Back-Button Prevention
 */
function logoutUser() {
    localStorage.removeItem('argo_pov');
    localStorage.removeItem('user_role');
    localStorage.removeItem('role');
    localStorage.removeItem('token');
    localStorage.removeItem('argo_token');
    localStorage.removeItem('argo_user');
    localStorage.removeItem('organization_id');
    sessionStorage.clear();
    window.location.replace('index.html');
}

// Expose utilities on window object for all modules
window.logoutUser = logoutUser;
window.getAuthToken = getAuthToken;
window.getAuthHeaders = getAuthHeaders;
window.getCurrentUser = getCurrentUser;
window.getNormalizedRole = getNormalizedRole;
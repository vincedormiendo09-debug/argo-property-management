/**
 * ARGO Property Management - Strict Navigation Guard & Session Security
 * Enforces strict role isolation: Admin, Owner, and Client/Tenant cannot cross boundaries.
 */
(function enforceRoleGuard() {
    // 1. Extract current filename
    const currentPath = window.location.pathname.split('/').pop() || 'index.html';

    // Shared pages accessible by any logged-in user
    const SHARED_PUBLIC_PAGES = ['index.html', ''];
    const SHARED_AUTHENTICATED_PAGES = ['notification.html', 'account.html', 'logout.html'];

    if (SHARED_PUBLIC_PAGES.includes(currentPath)) {
        return;
    }

    // 2. Retrieve session variables from LocalStorage
    const userRole = (localStorage.getItem('argo_pov') || '').toLowerCase();
    const orgId = localStorage.getItem('organization_id');

    // 3. Unauthenticated Guard
    if (!userRole || !orgId) {
        alert('🔒 Session Expired or Unauthenticated: Please sign in first.');
        window.location.href = 'index.html';
        return;
    }

    // Allow shared authenticated utility pages
    if (SHARED_AUTHENTICATED_PAGES.includes(currentPath)) {
        return;
    }

    // 4. Complete Whitelist Matrix per Role
    const roleRoutes = {
        admin: [
            'dashboard.html',
            'properties.html',
            'buildings.html',
            'units.html',
            'tenants.html',
            'owners.html',
            'property-ownership.html',
            'leases.html',
            'invoices.html',
            'rent-collection.html',
            'transaction.html',
            'utilities.html',
            'maintenance.html',
            'inspections.html',
            'documents.html',
            'reports.html',
            'settings.html'
        ],
        owner: [
            'owner-dashboard.html',
            'owner-properties.html',
            'owner-financials.html',
            'owner-reports.html'
        ],
        client: [
            'client-dashboard.html',
            'client-leases.html',
            'client-payments.html',
            'client-billing.html',
            'client-maintenance.html'
        ]
    };

    // 5. Strict Role Interceptor & Prefix Boundary Enforcement
    let isAuthorized = false;

    if (userRole === 'client') {
        isAuthorized = currentPath.startsWith('client-') || roleRoutes.client.includes(currentPath);
    } else if (userRole === 'owner') {
        isAuthorized = currentPath.startsWith('owner-') || roleRoutes.owner.includes(currentPath);
    } else if (userRole === 'admin') {
        // Admins cannot view tenant or owner specific portals
        isAuthorized = !currentPath.startsWith('client-') && 
                       !currentPath.startsWith('owner-') && 
                       (roleRoutes.admin.includes(currentPath) || !currentPath.includes('-'));
    }

    if (!isAuthorized) {
        alert(`🚫 Access Denied!\n\nYour account role (${userRole.toUpperCase()}) is not authorized to access '${currentPath}'.\n\nRedirecting to your workspace...`);

        if (userRole === 'admin') {
            window.location.href = 'dashboard.html';
        } else if (userRole === 'owner') {
            window.location.href = 'owner-dashboard.html';
        } else if (userRole === 'client') {
            window.location.href = 'client-dashboard.html';
        } else {
            window.location.href = 'index.html';
        }
    }
})();

/**
 * Global Logout Helper
 */
function logoutUser() {
    localStorage.removeItem('argo_pov');
    localStorage.removeItem('user_role');
    localStorage.removeItem('token');
    localStorage.removeItem('argo_user');
    window.location.href = 'index.html';
}
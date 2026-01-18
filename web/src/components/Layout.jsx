import { Link, useLocation } from 'react-router-dom';
import { useMsal, useAccount } from '@azure/msal-react';

function Layout({ children }) {
    const { instance, accounts } = useMsal();
    const account = useAccount(accounts[0] || {});
    const location = useLocation();

    const navItems = [
        { path: '/meetings', label: 'Meetings' },
        { path: '/actions', label: 'Actions' },
        { path: '/decisions', label: 'Decisions' },
    ];

    const handleLogout = () => {
        instance.logoutRedirect();
    };

    return (
        <div className="min-h-screen bg-gray-50">
            {/* Navigation */}
            <nav className="bg-white shadow-sm border-b border-gray-200">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex justify-between h-16">
                        {/* Logo & Nav Links */}
                        <div className="flex items-center">
                            <Link to="/meetings" className="flex items-center">
                                <span className="text-xl font-bold text-brand-600">Meeting Intelligence</span>
                            </Link>
                            <div className="hidden sm:ml-10 sm:flex sm:space-x-8">
                                {navItems.map((item) => (
                                    <Link
                                        key={item.path}
                                        to={item.path}
                                        className={`inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium ${location.pathname.startsWith(item.path)
                                                ? 'border-brand-500 text-gray-900'
                                                : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
                                            }`}
                                    >
                                        {item.label}
                                    </Link>
                                ))}
                            </div>
                        </div>

                        {/* User Menu */}
                        <div className="flex items-center space-x-4">
                            <span className="text-sm text-gray-700">
                                {account?.name || account?.username || 'User'}
                            </span>
                            <button
                                onClick={handleLogout}
                                className="text-sm text-gray-500 hover:text-gray-700"
                            >
                                Logout
                            </button>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {children}
            </main>
        </div>
    );
}

export default Layout;

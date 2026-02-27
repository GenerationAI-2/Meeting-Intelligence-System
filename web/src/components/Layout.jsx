import { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMsal, useAccount } from '@azure/msal-react';
import WorkspaceSwitcher from './WorkspaceSwitcher';
import { useWorkspace } from '../contexts/WorkspaceContext';

function Layout({ children }) {
    const { instance, accounts } = useMsal();
    const account = useAccount(accounts[0] || {});
    const location = useLocation();
    const navigate = useNavigate();
    const { isOrgAdmin } = useWorkspace();

    const [userMenuOpen, setUserMenuOpen] = useState(false);
    const userMenuRef = useRef(null);

    // Close dropdown on outside click
    useEffect(() => {
        function handleClick(e) {
            if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
                setUserMenuOpen(false);
            }
        }
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, []);

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

                        {/* Workspace + User Menu */}
                        <div className="flex items-center space-x-4">
                            <WorkspaceSwitcher />
                            <div className="relative" ref={userMenuRef}>
                                <button
                                    onClick={() => setUserMenuOpen(!userMenuOpen)}
                                    className="flex items-center space-x-1 px-3 py-1.5 rounded-md text-sm hover:bg-gray-100 cursor-pointer"
                                >
                                    <span className="text-gray-700">
                                        {account?.name || account?.username || 'User'}
                                    </span>
                                    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                    </svg>
                                </button>

                                {userMenuOpen && (
                                    <div className="absolute right-0 mt-1 w-48 bg-white rounded-md shadow-lg border border-gray-200 py-1 z-50">
                                        <button
                                            onClick={() => { navigate('/settings'); setUserMenuOpen(false); }}
                                            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                                        >
                                            Settings
                                        </button>
                                        {isOrgAdmin && (
                                            <button
                                                onClick={() => { navigate('/admin/workspaces'); setUserMenuOpen(false); }}
                                                className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                                            >
                                                Admin
                                            </button>
                                        )}
                                        <div className="border-t border-gray-100 my-1"></div>
                                        <button
                                            onClick={handleLogout}
                                            className="w-full text-left px-4 py-2 text-sm text-gray-500 hover:bg-gray-50"
                                        >
                                            Logout
                                        </button>
                                    </div>
                                )}
                            </div>
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

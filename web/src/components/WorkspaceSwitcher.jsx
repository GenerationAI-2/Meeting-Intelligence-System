import { useState, useRef, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';

const roleBadgeStyles = {
    chair: 'bg-purple-100 text-purple-800',
    member: 'bg-blue-100 text-blue-800',
    viewer: 'bg-gray-100 text-gray-800',
};

function RoleBadge({ role }) {
    const label = role.charAt(0).toUpperCase() + role.slice(1);
    return (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${roleBadgeStyles[role] || roleBadgeStyles.viewer}`}>
            {label}
        </span>
    );
}

function WorkspaceSwitcher() {
    const { workspaces, activeWorkspace, loading, switchWorkspace } = useWorkspace();
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    // Close dropdown on outside click
    useEffect(() => {
        function handleClick(e) {
            if (ref.current && !ref.current.contains(e.target)) {
                setOpen(false);
            }
        }
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, []);

    if (loading || !activeWorkspace) {
        return null;
    }

    // Don't show switcher if user only has one workspace
    const showDropdown = workspaces.length > 1;

    return (
        <div className="relative" ref={ref}>
            <button
                onClick={() => showDropdown && setOpen(!open)}
                className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-sm ${
                    showDropdown
                        ? 'hover:bg-gray-100 cursor-pointer'
                        : 'cursor-default'
                }`}
            >
                <span className="font-medium text-gray-900">{activeWorkspace.display_name}</span>
                <RoleBadge role={activeWorkspace.role} />
                {activeWorkspace.is_archived && (
                    <span className="text-xs text-gray-400">(Archived)</span>
                )}
                {showDropdown && (
                    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                )}
            </button>

            {open && (
                <div className="absolute right-0 mt-1 w-64 bg-white rounded-md shadow-lg border border-gray-200 py-1 z-50">
                    {workspaces.map((ws) => (
                        <button
                            key={ws.id}
                            onClick={() => {
                                switchWorkspace(ws.id);
                                setOpen(false);
                            }}
                            className={`w-full text-left px-4 py-2 text-sm flex items-center justify-between hover:bg-gray-50 ${
                                ws.id === activeWorkspace.id ? 'bg-brand-50' : ''
                            } ${ws.is_archived ? 'opacity-60' : ''}`}
                        >
                            <span className="truncate">
                                {ws.display_name}
                                {ws.is_archived && <span className="text-xs text-gray-400 ml-1">(Archived)</span>}
                            </span>
                            <RoleBadge role={ws.role} />
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

export default WorkspaceSwitcher;

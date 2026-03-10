import { useState, useEffect, Fragment } from 'react';
import { Navigate } from 'react-router-dom';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { workspaceApi } from '../services/api';

function WorkspaceAdmin() {
    const { isOrgAdmin, permissions, activeWorkspace, refreshWorkspaces } = useWorkspace();
    const [workspaces, setWorkspaces] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedWorkspace, setSelectedWorkspace] = useState(null);
    const [members, setMembers] = useState([]);
    const [membersLoading, setMembersLoading] = useState(false);

    // Create workspace form
    const [showCreateForm, setShowCreateForm] = useState(false);
    const [createName, setCreateName] = useState('');
    const [createDisplayName, setCreateDisplayName] = useState('');
    const [createError, setCreateError] = useState(null);
    const [creating, setCreating] = useState(false);

    // Add member form
    const [showAddMember, setShowAddMember] = useState(false);
    const [memberEmail, setMemberEmail] = useState('');
    const [memberDisplayName, setMemberDisplayName] = useState('');
    const [memberRole, setMemberRole] = useState('member');
    const [addMemberError, setAddMemberError] = useState(null);

    // Token management
    const [tokenUserId, setTokenUserId] = useState(null);
    const [memberTokens, setMemberTokens] = useState([]);
    const [tokensLoading, setTokensLoading] = useState(false);
    const [tokenError, setTokenError] = useState(null);
    const [tokenClientName, setTokenClientName] = useState('');
    const [tokenExpiresDays, setTokenExpiresDays] = useState('');
    const [creatingToken, setCreatingToken] = useState(false);
    const [newAdminToken, setNewAdminToken] = useState(null);
    const [tokenCopied, setTokenCopied] = useState(false);
    const [revokingTokenId, setRevokingTokenId] = useState(null);

    useEffect(() => {
        loadWorkspaces();
    }, []);

    async function loadWorkspaces() {
        try {
            setLoading(true);
            const data = await workspaceApi.listWorkspaces();
            setWorkspaces(data.workspaces || []);
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    async function loadMembers(wsId) {
        try {
            setMembersLoading(true);
            const data = await workspaceApi.listMembers(wsId);
            setMembers(data.members || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setMembersLoading(false);
        }
    }

    function selectWorkspace(ws) {
        setSelectedWorkspace(ws);
        loadMembers(ws.id);
        setShowAddMember(false);
        setAddMemberError(null);
        setTokenUserId(null);
        setNewAdminToken(null);
    }

    async function handleCreateWorkspace(e) {
        e.preventDefault();
        try {
            setCreating(true);
            setCreateError(null);
            await workspaceApi.createWorkspace({
                name: createName,
                display_name: createDisplayName,
            });
            setShowCreateForm(false);
            setCreateName('');
            setCreateDisplayName('');
            loadWorkspaces();
            refreshWorkspaces();
        } catch (err) {
            setCreateError(err.message);
        } finally {
            setCreating(false);
        }
    }

    async function handleArchiveToggle(ws) {
        try {
            await workspaceApi.archiveWorkspace(ws.id, !ws.is_archived);
            loadWorkspaces();
            refreshWorkspaces();
        } catch (err) {
            setError(err.message);
        }
    }

    async function handleAddMember(e) {
        e.preventDefault();
        if (!selectedWorkspace) return;
        try {
            setAddMemberError(null);
            await workspaceApi.addMember(selectedWorkspace.id, {
                email: memberEmail,
                display_name: memberDisplayName || undefined,
                role: memberRole,
            });
            setShowAddMember(false);
            setMemberEmail('');
            setMemberDisplayName('');
            setMemberRole('member');
            loadMembers(selectedWorkspace.id);
        } catch (err) {
            setAddMemberError(err.message);
        }
    }

    async function handleRoleChange(userId, newRole) {
        if (!selectedWorkspace) return;
        try {
            await workspaceApi.updateMemberRole(selectedWorkspace.id, userId, newRole);
            loadMembers(selectedWorkspace.id);
        } catch (err) {
            setError(err.message);
        }
    }

    async function handleRemoveMember(userId, email) {
        if (!selectedWorkspace) return;
        if (!confirm(`Remove ${email} from ${selectedWorkspace.display_name}?`)) return;
        try {
            await workspaceApi.removeMember(selectedWorkspace.id, userId);
            if (tokenUserId === userId) {
                setTokenUserId(null);
                setNewAdminToken(null);
            }
            loadMembers(selectedWorkspace.id);
        } catch (err) {
            setError(err.message);
        }
    }

    // --- Token management handlers ---

    async function loadMemberTokens(userId) {
        try {
            setTokensLoading(true);
            setTokenError(null);
            const data = await workspaceApi.listUserTokens(userId);
            setMemberTokens(data.tokens || []);
        } catch (err) {
            setTokenError(err.message);
        } finally {
            setTokensLoading(false);
        }
    }

    function toggleTokenPanel(userId) {
        if (tokenUserId === userId) {
            setTokenUserId(null);
            setMemberTokens([]);
            setNewAdminToken(null);
            setTokenError(null);
        } else {
            setTokenUserId(userId);
            setNewAdminToken(null);
            setTokenError(null);
            setRevokingTokenId(null);
            loadMemberTokens(userId);
        }
    }

    async function handleCreateAdminToken(e, userId) {
        e.preventDefault();
        try {
            setCreatingToken(true);
            setTokenError(null);
            const data = { client_name: tokenClientName };
            if (tokenExpiresDays) {
                data.expires_days = parseInt(tokenExpiresDays, 10);
            }
            const result = await workspaceApi.createUserToken(userId, data);
            setNewAdminToken(result);
            setTokenCopied(false);
            setTokenClientName('');
            setTokenExpiresDays('');
            loadMemberTokens(userId);
        } catch (err) {
            setTokenError(err.message);
        } finally {
            setCreatingToken(false);
        }
    }

    async function handleRevokeAdminToken(userId, tokenId) {
        try {
            await workspaceApi.revokeUserToken(userId, tokenId);
            setRevokingTokenId(null);
            loadMemberTokens(userId);
        } catch (err) {
            setTokenError(err.message);
        }
    }

    function handleCopyAdminToken() {
        if (newAdminToken?.token) {
            navigator.clipboard.writeText(newAdminToken.token);
            setTokenCopied(true);
            setTimeout(() => setTokenCopied(false), 2000);
        }
    }

    function formatDate(dateStr) {
        if (!dateStr) return 'Never';
        return new Date(dateStr).toLocaleDateString('en-NZ', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
        });
    }

    if (!isOrgAdmin) {
        return <Navigate to="/meetings" replace />;
    }

    if (loading) {
        return (
            <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-600"></div>
            </div>
        );
    }

    const activeTokens = memberTokens.filter(t => t.is_active);
    const revokedTokens = memberTokens.filter(t => !t.is_active);

    return (
        <div>
            <div className="flex items-center justify-between mb-6">
                <h1 className="text-2xl font-bold text-gray-900">Workspace Administration</h1>
                {isOrgAdmin && (
                    <button
                        onClick={() => setShowCreateForm(!showCreateForm)}
                        className="px-4 py-2 bg-brand-600 text-white rounded-md hover:bg-brand-700 text-sm font-medium"
                    >
                        Create Workspace
                    </button>
                )}
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
                    {error}
                    <button onClick={() => setError(null)} className="ml-2 text-red-500 hover:text-red-700">&times;</button>
                </div>
            )}

            {/* Create Workspace Form */}
            {showCreateForm && (
                <div className="mb-6 p-4 bg-white border border-gray-200 rounded-lg shadow-sm">
                    <h2 className="text-lg font-semibold mb-3">Create New Workspace</h2>
                    <form onSubmit={handleCreateWorkspace} className="space-y-3">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                Slug (lowercase, hyphens allowed)
                            </label>
                            <input
                                type="text"
                                value={createName}
                                onChange={(e) => setCreateName(e.target.value)}
                                pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$"
                                required
                                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
                                placeholder="e.g. board, ops-team"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                Display Name
                            </label>
                            <input
                                type="text"
                                value={createDisplayName}
                                onChange={(e) => setCreateDisplayName(e.target.value)}
                                required
                                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
                                placeholder="e.g. Board, Operations Team"
                            />
                        </div>
                        {createError && (
                            <p className="text-sm text-red-600">{createError}</p>
                        )}
                        <div className="flex space-x-2">
                            <button
                                type="submit"
                                disabled={creating}
                                className="px-4 py-2 bg-brand-600 text-white rounded-md hover:bg-brand-700 text-sm font-medium disabled:opacity-50"
                            >
                                {creating ? 'Creating...' : 'Create'}
                            </button>
                            <button
                                type="button"
                                onClick={() => setShowCreateForm(false)}
                                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 text-sm"
                            >
                                Cancel
                            </button>
                        </div>
                    </form>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Workspace List */}
                <div className="lg:col-span-1">
                    <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
                        <div className="p-4 border-b border-gray-200">
                            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Workspaces</h2>
                        </div>
                        <ul className="divide-y divide-gray-100">
                            {workspaces.map((ws) => (
                                <li key={ws.id}>
                                    <button
                                        onClick={() => selectWorkspace(ws)}
                                        className={`w-full text-left px-4 py-3 hover:bg-gray-50 ${
                                            selectedWorkspace?.id === ws.id ? 'bg-brand-50 border-l-2 border-brand-500' : ''
                                        }`}
                                    >
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <p className="text-sm font-medium text-gray-900">{ws.display_name}</p>
                                                <p className="text-xs text-gray-500">{ws.name}</p>
                                            </div>
                                            <div className="flex items-center space-x-2">
                                                {ws.is_archived && (
                                                    <span className="text-xs text-orange-600 bg-orange-50 px-1.5 py-0.5 rounded">Archived</span>
                                                )}
                                                {ws.is_default && (
                                                    <span className="text-xs text-green-600 bg-green-50 px-1.5 py-0.5 rounded">Default</span>
                                                )}
                                            </div>
                                        </div>
                                    </button>
                                </li>
                            ))}
                            {workspaces.length === 0 && (
                                <li className="px-4 py-6 text-center text-sm text-gray-500">No workspaces found</li>
                            )}
                        </ul>
                    </div>
                </div>

                {/* Member Management */}
                <div className="lg:col-span-2">
                    {selectedWorkspace ? (
                        <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
                            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
                                <div>
                                    <h2 className="text-lg font-semibold text-gray-900">{selectedWorkspace.display_name}</h2>
                                    <p className="text-sm text-gray-500">
                                        {selectedWorkspace.name} &middot; {selectedWorkspace.db_name}
                                        {selectedWorkspace.is_archived && ' \u00b7 Archived'}
                                    </p>
                                </div>
                                <div className="flex items-center space-x-2">
                                    {isOrgAdmin && (
                                        <button
                                            onClick={() => handleArchiveToggle(selectedWorkspace)}
                                            className={`px-3 py-1.5 text-sm rounded-md ${
                                                selectedWorkspace.is_archived
                                                    ? 'bg-green-50 text-green-700 hover:bg-green-100'
                                                    : 'bg-orange-50 text-orange-700 hover:bg-orange-100'
                                            }`}
                                        >
                                            {selectedWorkspace.is_archived ? 'Unarchive' : 'Archive'}
                                        </button>
                                    )}
                                    <button
                                        onClick={() => setShowAddMember(!showAddMember)}
                                        className="px-3 py-1.5 bg-brand-600 text-white rounded-md hover:bg-brand-700 text-sm"
                                    >
                                        Add Member
                                    </button>
                                </div>
                            </div>

                            {/* Add Member Form */}
                            {showAddMember && (
                                <div className="p-4 bg-gray-50 border-b border-gray-200">
                                    <form onSubmit={handleAddMember} className="flex items-end space-x-3">
                                        <div className="flex-1">
                                            <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
                                            <input
                                                type="email"
                                                value={memberEmail}
                                                onChange={(e) => setMemberEmail(e.target.value)}
                                                required
                                                className="w-full px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
                                                placeholder="user@example.com"
                                            />
                                        </div>
                                        <div className="flex-1">
                                            <label className="block text-xs font-medium text-gray-600 mb-1">Display Name</label>
                                            <input
                                                type="text"
                                                value={memberDisplayName}
                                                onChange={(e) => setMemberDisplayName(e.target.value)}
                                                className="w-full px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
                                                placeholder="Optional"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-medium text-gray-600 mb-1">Role</label>
                                            <select
                                                value={memberRole}
                                                onChange={(e) => setMemberRole(e.target.value)}
                                                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
                                            >
                                                <option value="viewer">Viewer</option>
                                                <option value="member">Member</option>
                                                <option value="chair">Chair</option>
                                            </select>
                                        </div>
                                        <button
                                            type="submit"
                                            className="px-4 py-1.5 bg-brand-600 text-white rounded-md hover:bg-brand-700 text-sm"
                                        >
                                            Add
                                        </button>
                                    </form>
                                    {addMemberError && (
                                        <p className="mt-2 text-sm text-red-600">{addMemberError}</p>
                                    )}
                                </div>
                            )}

                            {/* Members Table */}
                            {membersLoading ? (
                                <div className="flex justify-center py-8">
                                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
                                </div>
                            ) : (
                                <table className="min-w-full">
                                    <thead>
                                        <tr className="bg-gray-50 border-b border-gray-200">
                                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Role</th>
                                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Added</th>
                                            <th className="px-4 py-2"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                        {members.map((m) => (
                                            <Fragment key={m.user_id}>
                                                <tr className="hover:bg-gray-50">
                                                    <td className="px-4 py-2 text-sm text-gray-900">{m.email}</td>
                                                    <td className="px-4 py-2 text-sm text-gray-600">{m.display_name || '\u2014'}</td>
                                                    <td className="px-4 py-2">
                                                        <select
                                                            value={m.role}
                                                            onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                                                            className="text-sm border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-brand-500"
                                                        >
                                                            <option value="viewer">Viewer</option>
                                                            <option value="member">Member</option>
                                                            <option value="chair">Chair</option>
                                                        </select>
                                                    </td>
                                                    <td className="px-4 py-2 text-sm text-gray-500">
                                                        {m.added_at ? new Date(m.added_at).toLocaleDateString() : '\u2014'}
                                                    </td>
                                                    <td className="px-4 py-2 text-right space-x-3">
                                                        <button
                                                            onClick={() => toggleTokenPanel(m.user_id)}
                                                            className={`text-sm ${
                                                                tokenUserId === m.user_id
                                                                    ? 'text-brand-600 font-medium'
                                                                    : 'text-gray-500 hover:text-gray-700'
                                                            }`}
                                                        >
                                                            Tokens
                                                        </button>
                                                        <button
                                                            onClick={() => handleRemoveMember(m.user_id, m.email)}
                                                            className="text-sm text-red-600 hover:text-red-800"
                                                        >
                                                            Remove
                                                        </button>
                                                    </td>
                                                </tr>

                                                {/* Expandable Token Panel */}
                                                {tokenUserId === m.user_id && (
                                                    <tr>
                                                        <td colSpan={5} className="px-4 py-0 bg-gray-50">
                                                            <div className="py-3">
                                                                <h3 className="text-sm font-semibold text-gray-700 mb-3">
                                                                    Tokens for {m.email}
                                                                </h3>

                                                                {tokenError && (
                                                                    <div className="mb-3 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">
                                                                        {tokenError}
                                                                        <button onClick={() => setTokenError(null)} className="ml-2 text-red-500 hover:text-red-700">&times;</button>
                                                                    </div>
                                                                )}

                                                                {/* Create Token Form */}
                                                                <form onSubmit={(e) => handleCreateAdminToken(e, m.user_id)} className="flex items-end space-x-3 mb-3">
                                                                    <div className="flex-1">
                                                                        <label className="block text-xs font-medium text-gray-600 mb-1">Token Name</label>
                                                                        <input
                                                                            type="text"
                                                                            value={tokenClientName}
                                                                            onChange={(e) => setTokenClientName(e.target.value)}
                                                                            required
                                                                            maxLength={255}
                                                                            className="w-full px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
                                                                            placeholder="e.g. Claude Desktop, Copilot"
                                                                        />
                                                                    </div>
                                                                    <div>
                                                                        <label className="block text-xs font-medium text-gray-600 mb-1">Expires</label>
                                                                        <select
                                                                            value={tokenExpiresDays}
                                                                            onChange={(e) => setTokenExpiresDays(e.target.value)}
                                                                            className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
                                                                        >
                                                                            <option value="">No expiry</option>
                                                                            <option value="30">30 days</option>
                                                                            <option value="90">90 days</option>
                                                                            <option value="365">1 year</option>
                                                                        </select>
                                                                    </div>
                                                                    <button
                                                                        type="submit"
                                                                        disabled={creatingToken}
                                                                        className="px-4 py-1.5 bg-brand-600 text-white rounded-md hover:bg-brand-700 text-sm font-medium disabled:opacity-50"
                                                                    >
                                                                        {creatingToken ? 'Generating...' : 'Generate Token'}
                                                                    </button>
                                                                </form>

                                                                {/* Newly Created Token Display */}
                                                                {newAdminToken && (
                                                                    <div className="mb-3 p-3 bg-green-50 border border-green-200 rounded">
                                                                        <div className="flex items-start justify-between">
                                                                            <div className="flex-1">
                                                                                <p className="text-sm font-medium text-green-800 mb-2">
                                                                                    Token created. Copy it now — you won't be able to see it again.
                                                                                </p>
                                                                                <div className="flex items-center space-x-2">
                                                                                    <code className="flex-1 px-3 py-2 bg-white border border-green-200 rounded text-sm font-mono text-gray-800 select-all break-all">
                                                                                        {newAdminToken.token}
                                                                                    </code>
                                                                                    <button
                                                                                        onClick={handleCopyAdminToken}
                                                                                        className="px-3 py-2 bg-white border border-green-200 rounded text-sm hover:bg-green-50"
                                                                                    >
                                                                                        {tokenCopied ? 'Copied' : 'Copy'}
                                                                                    </button>
                                                                                </div>
                                                                            </div>
                                                                            <button
                                                                                onClick={() => setNewAdminToken(null)}
                                                                                className="ml-3 text-green-600 hover:text-green-800 text-lg"
                                                                            >
                                                                                &times;
                                                                            </button>
                                                                        </div>
                                                                    </div>
                                                                )}

                                                                {/* Token List */}
                                                                {tokensLoading ? (
                                                                    <div className="flex justify-center py-4">
                                                                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-brand-600"></div>
                                                                    </div>
                                                                ) : (
                                                                    <table className="min-w-full text-sm">
                                                                        <thead>
                                                                            <tr className="border-b border-gray-200">
                                                                                <th className="py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                                                                                <th className="py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                                                                                <th className="py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Created By</th>
                                                                                <th className="py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Expires</th>
                                                                                <th className="py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                                                                <th className="py-1.5"></th>
                                                                            </tr>
                                                                        </thead>
                                                                        <tbody className="divide-y divide-gray-100">
                                                                            {activeTokens.map((t) => (
                                                                                <tr key={t.id}>
                                                                                    <td className="py-1.5 text-gray-900">{t.client_name}</td>
                                                                                    <td className="py-1.5 text-gray-500">{formatDate(t.created_at)}</td>
                                                                                    <td className="py-1.5 text-gray-500">{t.created_by || '\u2014'}</td>
                                                                                    <td className="py-1.5 text-gray-500">{formatDate(t.expires_at)}</td>
                                                                                    <td className="py-1.5">
                                                                                        <span className="text-xs bg-green-100 text-green-800 rounded px-2 py-0.5">Active</span>
                                                                                    </td>
                                                                                    <td className="py-1.5 text-right">
                                                                                        {revokingTokenId === t.id ? (
                                                                                            <span>
                                                                                                <span className="text-gray-500 mr-2">Revoke?</span>
                                                                                                <button
                                                                                                    onClick={() => handleRevokeAdminToken(m.user_id, t.id)}
                                                                                                    className="text-red-600 hover:text-red-800 mr-2"
                                                                                                >
                                                                                                    Yes
                                                                                                </button>
                                                                                                <button
                                                                                                    onClick={() => setRevokingTokenId(null)}
                                                                                                    className="text-gray-500 hover:text-gray-700"
                                                                                                >
                                                                                                    No
                                                                                                </button>
                                                                                            </span>
                                                                                        ) : (
                                                                                            <button
                                                                                                onClick={() => setRevokingTokenId(t.id)}
                                                                                                className="text-red-600 hover:text-red-800"
                                                                                            >
                                                                                                Revoke
                                                                                            </button>
                                                                                        )}
                                                                                    </td>
                                                                                </tr>
                                                                            ))}
                                                                            {revokedTokens.map((t) => (
                                                                                <tr key={t.id} className="bg-gray-50">
                                                                                    <td className="py-1.5 text-gray-400">{t.client_name}</td>
                                                                                    <td className="py-1.5 text-gray-400">{formatDate(t.created_at)}</td>
                                                                                    <td className="py-1.5 text-gray-400">{t.created_by || '\u2014'}</td>
                                                                                    <td className="py-1.5 text-gray-400">{formatDate(t.expires_at)}</td>
                                                                                    <td className="py-1.5">
                                                                                        <span className="text-xs bg-gray-100 text-gray-500 rounded px-2 py-0.5">Revoked</span>
                                                                                    </td>
                                                                                    <td className="py-1.5"></td>
                                                                                </tr>
                                                                            ))}
                                                                            {memberTokens.length === 0 && (
                                                                                <tr>
                                                                                    <td colSpan={6} className="py-4 text-center text-gray-500">
                                                                                        No tokens. Generate one above.
                                                                                    </td>
                                                                                </tr>
                                                                            )}
                                                                        </tbody>
                                                                    </table>
                                                                )}
                                                            </div>
                                                        </td>
                                                    </tr>
                                                )}
                                            </Fragment>
                                        ))}
                                        {members.length === 0 && (
                                            <tr>
                                                <td colSpan={5} className="px-4 py-6 text-center text-sm text-gray-500">
                                                    No members found
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    ) : (
                        <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-12 text-center">
                            <p className="text-gray-500">Select a workspace to manage members</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default WorkspaceAdmin;

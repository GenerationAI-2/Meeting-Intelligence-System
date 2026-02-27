import { useState, useEffect } from 'react';
import { tokensApi } from '../services/api';

function Settings() {
    const [tokens, setTokens] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [provisioned, setProvisioned] = useState(true);
    const [hasMemberships, setHasMemberships] = useState(true);

    // Create form
    const [clientName, setClientName] = useState('');
    const [expiresDays, setExpiresDays] = useState('');
    const [creating, setCreating] = useState(false);
    const [createError, setCreateError] = useState(null);

    // Newly created token (shown once)
    const [newToken, setNewToken] = useState(null);
    const [copied, setCopied] = useState(false);

    // Revoke confirmation
    const [revoking, setRevoking] = useState(null);

    useEffect(() => {
        loadTokens();
    }, []);

    async function loadTokens() {
        try {
            setLoading(true);
            const data = await tokensApi.list();
            setTokens(data.tokens || []);
            setProvisioned(data.provisioned !== false);
            setHasMemberships(data.has_memberships !== false);
            setError(null);
        } catch (err) {
            if (err.message.includes('404')) {
                // Workspace mode not configured
                setProvisioned(false);
            } else {
                setError(err.message);
            }
        } finally {
            setLoading(false);
        }
    }

    async function handleCreate(e) {
        e.preventDefault();
        try {
            setCreating(true);
            setCreateError(null);
            const data = {
                client_name: clientName,
            };
            if (expiresDays) {
                data.expires_days = parseInt(expiresDays, 10);
            }
            const result = await tokensApi.create(data);
            setNewToken(result);
            setCopied(false);
            setClientName('');
            setExpiresDays('');
            loadTokens();
        } catch (err) {
            setCreateError(err.message);
        } finally {
            setCreating(false);
        }
    }

    async function handleRevoke(tokenId) {
        try {
            await tokensApi.revoke(tokenId);
            setRevoking(null);
            loadTokens();
        } catch (err) {
            setError(err.message);
        }
    }

    function handleCopy() {
        if (newToken?.token) {
            navigator.clipboard.writeText(newToken.token);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
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

    if (loading) {
        return (
            <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-600"></div>
            </div>
        );
    }

    // Not provisioned in MI
    if (!provisioned) {
        return (
            <div>
                <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>
                <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-8 text-center">
                    <p className="text-gray-600 mb-2">
                        You're not set up in Meeting Intelligence yet.
                    </p>
                    <p className="text-gray-500 text-sm">
                        Ask your administrator to add you to a workspace.
                    </p>
                </div>
            </div>
        );
    }

    // Provisioned but no memberships
    if (!hasMemberships) {
        return (
            <div>
                <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>
                <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-8 text-center">
                    <p className="text-gray-600 mb-2">
                        You don't have any workspace memberships.
                    </p>
                    <p className="text-gray-500 text-sm">
                        Contact your administrator to be added to a workspace before generating tokens.
                    </p>
                </div>
            </div>
        );
    }

    const activeTokens = tokens.filter(t => t.is_active);
    const revokedTokens = tokens.filter(t => !t.is_active);

    return (
        <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
                    {error}
                    <button onClick={() => setError(null)} className="ml-2 text-red-500 hover:text-red-700">&times;</button>
                </div>
            )}

            {/* Personal Access Tokens */}
            <div className="bg-white border border-gray-200 rounded-lg shadow-sm mb-6">
                <div className="p-4 border-b border-gray-200">
                    <h2 className="text-lg font-semibold text-gray-900">Personal Access Tokens</h2>
                    <p className="text-sm text-gray-500 mt-1">
                        Generate tokens to connect your AI tools to Meeting Intelligence.
                    </p>
                </div>

                {/* Create Token Form */}
                <div className="p-4 border-b border-gray-200 bg-gray-50">
                    <form onSubmit={handleCreate} className="flex items-end space-x-3">
                        <div className="flex-1">
                            <label className="block text-xs font-medium text-gray-600 mb-1">Token Name</label>
                            <input
                                type="text"
                                value={clientName}
                                onChange={(e) => setClientName(e.target.value)}
                                required
                                maxLength={255}
                                className="w-full px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
                                placeholder="e.g. Claude Desktop, Copilot"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Expires</label>
                            <select
                                value={expiresDays}
                                onChange={(e) => setExpiresDays(e.target.value)}
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
                            disabled={creating}
                            className="px-4 py-1.5 bg-brand-600 text-white rounded-md hover:bg-brand-700 text-sm font-medium disabled:opacity-50"
                        >
                            {creating ? 'Generating...' : 'Generate Token'}
                        </button>
                    </form>
                    {createError && (
                        <p className="mt-2 text-sm text-red-600">{createError}</p>
                    )}
                </div>

                {/* Newly Created Token Display */}
                {newToken && (
                    <div className="p-4 border-b border-gray-200 bg-green-50">
                        <div className="flex items-start justify-between">
                            <div className="flex-1">
                                <p className="text-sm font-medium text-green-800 mb-2">
                                    Token created. Copy it now — you won't be able to see it again.
                                </p>
                                <div className="flex items-center space-x-2">
                                    <code className="flex-1 px-3 py-2 bg-white border border-green-200 rounded text-sm font-mono text-gray-800 select-all break-all">
                                        {newToken.token}
                                    </code>
                                    <button
                                        onClick={handleCopy}
                                        className="px-3 py-2 bg-white border border-green-200 rounded text-sm hover:bg-green-50"
                                    >
                                        {copied ? 'Copied' : 'Copy'}
                                    </button>
                                </div>
                            </div>
                            <button
                                onClick={() => setNewToken(null)}
                                className="ml-3 text-green-600 hover:text-green-800 text-lg"
                            >
                                &times;
                            </button>
                        </div>
                    </div>
                )}

                {/* Active Tokens Table */}
                <table className="min-w-full">
                    <thead>
                        <tr className="bg-gray-50 border-b border-gray-200">
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Expires</th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                            <th className="px-4 py-2"></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                        {activeTokens.map((t) => (
                            <tr key={t.id} className="hover:bg-gray-50">
                                <td className="px-4 py-2 text-sm text-gray-900">{t.client_name}</td>
                                <td className="px-4 py-2 text-sm text-gray-500">{formatDate(t.created_at)}</td>
                                <td className="px-4 py-2 text-sm text-gray-500">{formatDate(t.expires_at)}</td>
                                <td className="px-4 py-2">
                                    <span className="text-xs bg-green-100 text-green-800 rounded px-2 py-0.5">Active</span>
                                </td>
                                <td className="px-4 py-2 text-right">
                                    {revoking === t.id ? (
                                        <span className="text-sm">
                                            <span className="text-gray-500 mr-2">Revoke?</span>
                                            <button
                                                onClick={() => handleRevoke(t.id)}
                                                className="text-red-600 hover:text-red-800 mr-2"
                                            >
                                                Yes
                                            </button>
                                            <button
                                                onClick={() => setRevoking(null)}
                                                className="text-gray-500 hover:text-gray-700"
                                            >
                                                No
                                            </button>
                                        </span>
                                    ) : (
                                        <button
                                            onClick={() => setRevoking(t.id)}
                                            className="text-sm text-red-600 hover:text-red-800"
                                        >
                                            Revoke
                                        </button>
                                    )}
                                </td>
                            </tr>
                        ))}
                        {revokedTokens.map((t) => (
                            <tr key={t.id} className="bg-gray-50">
                                <td className="px-4 py-2 text-sm text-gray-400">{t.client_name}</td>
                                <td className="px-4 py-2 text-sm text-gray-400">{formatDate(t.created_at)}</td>
                                <td className="px-4 py-2 text-sm text-gray-400">{formatDate(t.expires_at)}</td>
                                <td className="px-4 py-2">
                                    <span className="text-xs bg-gray-100 text-gray-500 rounded px-2 py-0.5">Revoked</span>
                                </td>
                                <td className="px-4 py-2"></td>
                            </tr>
                        ))}
                        {tokens.length === 0 && (
                            <tr>
                                <td colSpan={5} className="px-4 py-6 text-center text-sm text-gray-500">
                                    No tokens yet. Generate one above to connect your AI tools.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Connection Help */}
            <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
                <div className="p-4 border-b border-gray-200">
                    <h2 className="text-lg font-semibold text-gray-900">Connecting Your AI Tools</h2>
                </div>
                <div className="p-4 space-y-4 text-sm text-gray-600">
                    <div>
                        <h3 className="font-medium text-gray-900 mb-1">Claude Desktop</h3>
                        <p className="mb-2">Add to your Claude Desktop MCP server config:</p>
                        <pre className="px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono break-all whitespace-pre-wrap">
{`{
  "url": "${window.location.origin}/mcp",
  "headers": {
    "Authorization": "Bearer YOUR_TOKEN"
  }
}`}
                        </pre>
                    </div>
                    <div>
                        <h3 className="font-medium text-gray-900 mb-1">Other MCP Clients</h3>
                        <p className="mb-1">Connect to the Streamable HTTP endpoint:</p>
                        <code className="block px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono break-all">
                            {`${window.location.origin}/mcp`}
                        </code>
                        <p className="mt-1">Authenticate with a <strong>Bearer</strong> token in the Authorization header or an <strong>X-API-Key</strong> header.</p>
                    </div>
                    <p className="text-xs text-gray-400 mt-2">
                        Token revocation may take up to 5 minutes to take effect due to caching.
                    </p>
                </div>
            </div>
        </div>
    );
}

export default Settings;

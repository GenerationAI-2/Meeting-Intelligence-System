import { useState } from 'react';

function CopyButton({ text, label = 'Copy' }) {
    const [copied, setCopied] = useState(false);

    function handleCopy() {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }

    return (
        <button
            onClick={handleCopy}
            className="px-3 py-1.5 bg-white border border-gray-300 rounded text-xs font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-800 transition-colors whitespace-nowrap"
        >
            {copied ? 'Copied!' : label}
        </button>
    );
}

function CollapsibleSection({ title, children, defaultOpen = false }) {
    const [open, setOpen] = useState(defaultOpen);

    return (
        <div className="border border-gray-200 rounded-md">
            <button
                onClick={() => setOpen(!open)}
                className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-900 hover:bg-gray-50 transition-colors"
            >
                <span>{title}</span>
                <svg
                    className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {open && (
                <div className="px-4 pb-4 text-sm text-gray-600 border-t border-gray-200 pt-3">
                    {children}
                </div>
            )}
        </div>
    );
}

function ConnectYourAI({ token, hasActiveTokens }) {
    const serverUrl = window.location.origin;
    const hasToken = !!token;
    const connectionUrl = hasToken
        ? `${serverUrl}/mcp?token=${token}`
        : null;

    const desktopConfig = hasToken
        ? JSON.stringify({
            mcpServers: {
                'meeting-intelligence': {
                    command: 'npx',
                    args: ['-y', 'mcp-remote', `${serverUrl}/mcp?token=${token}`],
                },
            },
        }, null, 2)
        : null;

    return (
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
            <div className="p-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">Connect Your AI</h2>
                <p className="text-sm text-gray-500 mt-1">
                    Connect Claude, Copilot, or other MCP-compatible AI tools to Meeting Intelligence.
                </p>
            </div>

            <div className="p-4 space-y-4">
                {/* Connection URL */}
                {hasToken ? (
                    <div>
                        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                            Connection URL
                        </label>
                        <div className="flex items-center space-x-2">
                            <code className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-sm font-mono text-gray-800 break-all select-all">
                                {connectionUrl}
                            </code>
                            <CopyButton text={connectionUrl} />
                        </div>

                        <div className="flex items-center space-x-4 mt-3">
                            <div className="flex-1">
                                <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                                    Server URL
                                </label>
                                <div className="flex items-center space-x-2">
                                    <code className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono text-gray-600 break-all">
                                        {serverUrl}/mcp
                                    </code>
                                    <CopyButton text={`${serverUrl}/mcp`} />
                                </div>
                            </div>
                            <div className="flex-1">
                                <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                                    Token
                                </label>
                                <div className="flex items-center space-x-2">
                                    <code className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono text-gray-600 break-all">
                                        {token}
                                    </code>
                                    <CopyButton text={token} />
                                </div>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="px-4 py-6 bg-gray-50 border border-gray-200 rounded-md text-center">
                        {hasActiveTokens ? (
                            <>
                                <p className="text-sm text-gray-600 mb-1">
                                    Generate a new token above to see your pre-populated connection URL.
                                </p>
                                <p className="text-xs text-gray-400">
                                    If you saved a token previously, you can use it manually with: <code className="font-mono">{serverUrl}/mcp?token=YOUR_TOKEN</code>
                                </p>
                            </>
                        ) : (
                            <p className="text-sm text-gray-600">
                                Generate a token above to get your connection URL.
                            </p>
                        )}
                    </div>
                )}

                {/* Platform Instructions */}
                <div className="space-y-2 pt-2">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Setup Instructions</p>

                    <CollapsibleSection title="Claude.ai (Web)" defaultOpen={hasToken}>
                        <ol className="list-decimal list-inside space-y-2">
                            <li>
                                Go to <strong>claude.ai</strong> and open <strong>Settings</strong>
                            </li>
                            <li>
                                Navigate to <strong>Connectors</strong> and click <strong>Add custom connector</strong>
                            </li>
                            <li>
                                Paste the connection URL:
                                {hasToken ? (
                                    <div className="flex items-center space-x-2 mt-1.5">
                                        <code className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono break-all select-all">
                                            {connectionUrl}
                                        </code>
                                        <CopyButton text={connectionUrl} />
                                    </div>
                                ) : (
                                    <code className="block mt-1.5 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono break-all">
                                        {serverUrl}/mcp?token=YOUR_TOKEN
                                    </code>
                                )}
                            </li>
                            <li>Done — works immediately on both web and mobile</li>
                        </ol>
                    </CollapsibleSection>

                    <CollapsibleSection title="Claude Desktop (Config File)">
                        <ol className="list-decimal list-inside space-y-2">
                            <li>
                                Open your Claude Desktop config file:
                                <div className="mt-1.5 space-y-1">
                                    <div className="flex items-center space-x-2">
                                        <span className="text-xs text-gray-400 w-10">Mac</span>
                                        <code className="text-xs font-mono text-gray-600">~/Library/Application Support/Claude/claude_desktop_config.json</code>
                                    </div>
                                    <div className="flex items-center space-x-2">
                                        <span className="text-xs text-gray-400 w-10">Win</span>
                                        <code className="text-xs font-mono text-gray-600">%APPDATA%\Claude\claude_desktop_config.json</code>
                                    </div>
                                </div>
                            </li>
                            <li>
                                Add this configuration:
                                {hasToken ? (
                                    <div className="mt-1.5">
                                        <div className="flex items-start space-x-2">
                                            <pre className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono whitespace-pre-wrap break-all select-all">
                                                {desktopConfig}
                                            </pre>
                                            <CopyButton text={desktopConfig} />
                                        </div>
                                    </div>
                                ) : (
                                    <pre className="mt-1.5 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono whitespace-pre-wrap break-all">
{`{
  "mcpServers": {
    "meeting-intelligence": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${serverUrl}/mcp?token=YOUR_TOKEN"]
    }
  }
}`}
                                    </pre>
                                )}
                            </li>
                            <li>Restart Claude Desktop to apply the changes</li>
                        </ol>
                    </CollapsibleSection>

                    <CollapsibleSection title="Microsoft Copilot">
                        <p className="text-gray-500">
                            Copilot MCP connection support is coming soon. In the meantime, you can connect using any MCP-compatible client with the Streamable HTTP endpoint:
                        </p>
                        <div className="mt-2">
                            <code className="px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono block break-all">
                                {serverUrl}/mcp
                            </code>
                            <p className="mt-2 text-xs text-gray-400">
                                Authenticate with a <strong>Bearer</strong> token in the Authorization header, an <strong>X-API-Key</strong> header, or a <strong>?token=</strong> query parameter.
                            </p>
                        </div>
                    </CollapsibleSection>
                </div>

                <p className="text-xs text-gray-400">
                    Token revocation may take up to 5 minutes to take effect due to caching.
                </p>
            </div>
        </div>
    );
}

export default ConnectYourAI;

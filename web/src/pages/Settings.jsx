import { useState } from 'react';

function Settings() {
    const serverUrl = window.location.origin;

    return (
        <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

            {/* Connect Your AI */}
            <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
                <div className="p-4 border-b border-gray-200">
                    <h2 className="text-lg font-semibold text-gray-900">Connect Your AI</h2>
                    <p className="text-sm text-gray-500 mt-1">
                        Connect Claude, ChatGPT, or other MCP-compatible AI tools to Meeting Intelligence.
                    </p>
                </div>

                <div className="p-4 space-y-4">
                    <div>
                        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                            MCP Endpoint
                        </label>
                        <div className="flex items-center space-x-2">
                            <code className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-sm font-mono text-gray-800 break-all select-all">
                                {serverUrl}/mcp
                            </code>
                            <CopyButton text={`${serverUrl}/mcp`} />
                        </div>
                    </div>

                    <div className="p-3 bg-blue-50 border border-blue-200 rounded-md">
                        <p className="text-sm text-blue-800">
                            <strong>OAuth authentication is enabled.</strong> When you connect an AI tool to this endpoint,
                            you'll be redirected to sign in with your Microsoft account. No tokens required.
                        </p>
                    </div>

                    <div className="space-y-2 pt-2">
                        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Setup Instructions</p>

                        <CollapsibleSection title="Claude.ai (Web)">
                            <ol className="list-decimal list-inside space-y-2">
                                <li>Go to <strong>claude.ai</strong> and open <strong>Settings</strong></li>
                                <li>Navigate to <strong>Connectors</strong> and click <strong>Add custom connector</strong></li>
                                <li>
                                    Paste the MCP endpoint:
                                    <code className="block mt-1.5 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono break-all">
                                        {serverUrl}/mcp
                                    </code>
                                </li>
                                <li>Sign in with your Microsoft account when prompted</li>
                            </ol>
                        </CollapsibleSection>

                        <CollapsibleSection title="ChatGPT">
                            <ol className="list-decimal list-inside space-y-2">
                                <li>Go to <strong>ChatGPT</strong> and open a conversation</li>
                                <li>Click the <strong>tools icon</strong> and select <strong>Add MCP server</strong></li>
                                <li>
                                    Paste the MCP endpoint:
                                    <code className="block mt-1.5 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono break-all">
                                        {serverUrl}/mcp
                                    </code>
                                </li>
                                <li>Sign in with your Microsoft account when prompted</li>
                            </ol>
                        </CollapsibleSection>

                        <CollapsibleSection title="Claude Desktop">
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
                                    <pre className="mt-1.5 px-3 py-2 bg-gray-50 border border-gray-200 rounded text-xs font-mono whitespace-pre-wrap break-all">
{`{
  "mcpServers": {
    "meeting-intelligence": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${serverUrl}/mcp"]
    }
  }
}`}
                                    </pre>
                                </li>
                                <li>Restart Claude Desktop — you'll be prompted to sign in on first use</li>
                            </ol>
                        </CollapsibleSection>
                    </div>
                </div>
            </div>
        </div>
    );
}

function CopyButton({ text }) {
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
            {copied ? 'Copied!' : 'Copy'}
        </button>
    );
}

function CollapsibleSection({ title, children }) {
    const [open, setOpen] = useState(false);

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

export default Settings;

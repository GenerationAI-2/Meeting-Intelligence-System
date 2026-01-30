import { useState } from 'react';

export function ExpandableText({ text }) {
    const [expanded, setExpanded] = useState(false);

    if (!text) return <span>-</span>;

    return (
        <div
            onClick={(e) => {
                e.stopPropagation();
                setExpanded(!expanded);
            }}
            className="cursor-pointer hover:bg-gray-100 rounded p-1 -m-1"
        >
            <div className={!expanded ? 'line-clamp-2' : ''}>
                {text}
            </div>
            <span className="text-xs text-brand-600 hover:underline">
                {expanded ? '↑ Less' : '↓ More'}
            </span>
        </div>
    );
}

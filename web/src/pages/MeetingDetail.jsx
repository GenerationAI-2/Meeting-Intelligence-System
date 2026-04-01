import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { meetingsApi, actionsApi } from '../services/api';
import { useWorkspace } from '../contexts/WorkspaceContext';

function MeetingDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { permissions, userEmail } = useWorkspace();
    const [meeting, setMeeting] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [transcriptExpanded, setTranscriptExpanded] = useState(false);
    const [editing, setEditing] = useState(false);
    const [editForm, setEditForm] = useState({});
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        loadMeeting();
    }, [id]);

    async function loadMeeting() {
        try {
            setLoading(true);
            const data = await meetingsApi.get(id);
            setMeeting(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    function startEditing() {
        setEditForm({
            title: meeting.title || '',
            attendees: meeting.attendees || '',
            tags: meeting.tags || '',
        });
        setEditing(true);
    }

    async function handleSave(e) {
        e.preventDefault();
        try {
            setSaving(true);
            const updates = {};
            if (editForm.title !== meeting.title) updates.title = editForm.title;
            if (editForm.attendees !== (meeting.attendees || '')) updates.attendees = editForm.attendees || null;
            if (editForm.tags !== (meeting.tags || '')) updates.tags = editForm.tags || null;

            if (Object.keys(updates).length > 0) {
                await meetingsApi.update(id, updates);
                await loadMeeting();
            }
            setEditing(false);
        } catch (err) {
            setError(err.message);
        } finally {
            setSaving(false);
        }
    }

    async function handleActionStatusChange(actionId, newStatus) {
        try {
            await actionsApi.updateStatus(actionId, newStatus);
            setMeeting(prev => ({
                ...prev,
                actions: prev.actions.map(a =>
                    a.id === actionId ? { ...a, status: newStatus } : a
                ),
            }));
        } catch (err) {
            console.error('Failed to update action status:', err);
        }
    }

    function formatDate(dateStr) {
        if (!dateStr) return '-';
        const d = new Date(dateStr);
        const options = {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
        };
        // Only show time if it's not midnight (i.e. time data was actually provided)
        if (d.getHours() !== 0 || d.getMinutes() !== 0) {
            options.hour = '2-digit';
            options.minute = '2-digit';
        }
        return d.toLocaleDateString('en-NZ', options);
    }

    if (loading) {
        return (
            <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
            </div>
        );
    }

    if (error || !meeting) {
        return (
            <div className="card text-center py-12">
                <p className="text-red-600">{error || 'Meeting not found'}</p>
                <Link to="/meetings" className="btn-primary mt-4 inline-block">
                    Back to Meetings
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Back Link */}
            <Link to="/meetings" className="text-brand-600 hover:text-brand-700 flex items-center gap-1">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back to Meetings
            </Link>

            {editing ? (
                /* Edit Mode */
                <form onSubmit={handleSave} className="card">
                    <div className="flex items-center justify-between mb-4">
                        <h1 className="text-xl font-bold text-gray-900">Edit Meeting</h1>
                    </div>
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Title *</label>
                            <input
                                type="text"
                                required
                                value={editForm.title}
                                onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Attendees</label>
                            <input
                                type="text"
                                value={editForm.attendees}
                                onChange={(e) => setEditForm({ ...editForm, attendees: e.target.value })}
                                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2"
                                placeholder="Comma-separated names"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Tags</label>
                            <input
                                type="text"
                                value={editForm.tags}
                                onChange={(e) => setEditForm({ ...editForm, tags: e.target.value })}
                                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2"
                                placeholder="Comma-separated, lowercase"
                            />
                        </div>
                    </div>
                    <div className="mt-4 flex gap-2">
                        <button type="submit" disabled={saving} className="btn-primary disabled:opacity-50">
                            {saving ? 'Saving...' : 'Save Changes'}
                        </button>
                        <button type="button" onClick={() => setEditing(false)} className="btn-secondary">
                            Cancel
                        </button>
                    </div>
                </form>
            ) : (
                <>
                    {/* Header */}
                    <div className="card">
                        <div className="flex items-start justify-between">
                            <div>
                                <h1 className="text-2xl font-bold text-gray-900">{meeting.title}</h1>
                                <p className="text-gray-500 mt-1">{formatDate(meeting.date)}</p>
                            </div>
                            <div className="flex items-center gap-2">
                                {permissions.can_write && (permissions.is_chair_or_admin || meeting.created_by === userEmail) && (
                                    <button onClick={startEditing} className="btn-secondary text-sm">
                                        Edit
                                    </button>
                                )}
                                <span className={`px-3 py-1 text-sm rounded-full ${meeting.source === 'Fireflies'
                                        ? 'bg-purple-100 text-purple-800'
                                        : 'bg-gray-100 text-gray-800'
                                    }`}>
                                    {meeting.source}
                                </span>
                            </div>
                        </div>

                        {meeting.attendees && (
                            <div className="mt-4">
                                <h3 className="text-sm font-medium text-gray-500">Attendees</h3>
                                <p className="text-gray-900">{meeting.attendees}</p>
                            </div>
                        )}

                        {meeting.tags && (
                            <div className="mt-3">
                                <h3 className="text-sm font-medium text-gray-500">Tags</h3>
                                <div className="flex flex-wrap gap-1 mt-1">
                                    {meeting.tags.split(',').map((tag) => (
                                        <span key={tag.trim()} className="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600">
                                            {tag.trim()}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Summary */}
                    {meeting.summary && (
                        <div className="card">
                            <h2 className="text-lg font-semibold text-gray-900 mb-3">Summary</h2>
                            <div className="prose prose-gray max-w-none">
                                <ReactMarkdown>{meeting.summary}</ReactMarkdown>
                            </div>
                        </div>
                    )}

                    {/* Transcript (Collapsible) */}
                    {meeting.transcript && (
                        <div className="card">
                            <button
                                onClick={() => setTranscriptExpanded(!transcriptExpanded)}
                                className="w-full flex items-center justify-between text-left"
                            >
                                <h2 className="text-lg font-semibold text-gray-900">Transcript</h2>
                                <svg
                                    className={`w-5 h-5 text-gray-500 transition-transform ${transcriptExpanded ? 'rotate-180' : ''}`}
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                >
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                </svg>
                            </button>

                            {transcriptExpanded && (
                                <div className="mt-4 p-4 bg-gray-50 rounded-lg max-h-96 overflow-y-auto">
                                    <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono">
                                        {meeting.transcript}
                                    </pre>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Linked Decisions */}
                    {meeting.decisions && meeting.decisions.length > 0 && (
                        <div className="card">
                            <h2 className="text-lg font-semibold text-gray-900 mb-3">Decisions</h2>
                            <ul className="space-y-3">
                                {meeting.decisions.map((decision) => (
                                    <li key={decision.id} className="p-3 bg-gray-50 rounded-lg">
                                        <p className="text-gray-900">{decision.text}</p>
                                        {decision.context && (
                                            <p className="text-sm text-gray-500 mt-1">{decision.context}</p>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* Linked Actions */}
                    {meeting.actions && meeting.actions.length > 0 && (
                        <div className="card">
                            <h2 className="text-lg font-semibold text-gray-900 mb-3">Actions</h2>
                            <ul className="space-y-3">
                                {meeting.actions.map((action) => (
                                    <li key={action.id} className="p-3 bg-gray-50 rounded-lg flex items-center justify-between">
                                        <div>
                                            <p className="text-gray-900">{action.text}</p>
                                            <p className="text-sm text-gray-500">
                                                {action.owner} {action.due_date && `• Due ${action.due_date}`}
                                            </p>
                                        </div>
                                        {permissions.can_write ? (
                                            <select
                                                value={action.status}
                                                onChange={(e) => handleActionStatusChange(action.id, e.target.value)}
                                                className={`rounded pl-3 pr-8 py-1.5 text-xs border-0 cursor-pointer ${action.status === 'Complete'
                                                        ? 'bg-green-100 text-green-800'
                                                        : action.status === 'Parked'
                                                            ? 'bg-yellow-100 text-yellow-800'
                                                            : 'bg-blue-100 text-blue-800'
                                                    }`}
                                                style={{
                                                    appearance: 'none',
                                                    WebkitAppearance: 'none',
                                                    backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                                                    backgroundPosition: 'right 0.5rem center',
                                                    backgroundSize: '1.25em 1.25em',
                                                    backgroundRepeat: 'no-repeat'
                                                }}
                                            >
                                                <option value="Open">Open</option>
                                                <option value="Complete">Complete</option>
                                                <option value="Parked">Parked</option>
                                            </select>
                                        ) : (
                                            <span className={`px-2 py-1 text-xs rounded-full ${action.status === 'Complete'
                                                    ? 'bg-green-100 text-green-800'
                                                    : action.status === 'Parked'
                                                        ? 'bg-yellow-100 text-yellow-800'
                                                        : 'bg-blue-100 text-blue-800'
                                                }`}>
                                                {action.status}
                                            </span>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* Delete — chairs and org admins only */}
                    {permissions.is_chair_or_admin && (
                        <div className="card">
                            <button
                                onClick={async () => {
                                    if (!confirm('Delete this meeting and all linked actions and decisions? This cannot be undone.')) return;
                                    try {
                                        await meetingsApi.delete(id);
                                        navigate('/meetings');
                                    } catch (err) {
                                        console.error('Delete failed:', err);
                                    }
                                }}
                                className="px-4 py-2 rounded-lg text-sm font-medium bg-red-50 text-red-700 hover:bg-red-100"
                            >
                                Delete Meeting
                            </button>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

export default MeetingDetail;

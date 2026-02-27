import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { actionsApi } from '../services/api';
import { useWorkspace } from '../contexts/WorkspaceContext';

function ActionDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { permissions } = useWorkspace();
    const [action, setAction] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [editing, setEditing] = useState(false);
    const [editForm, setEditForm] = useState({});
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        loadAction();
    }, [id]);

    async function loadAction() {
        try {
            setLoading(true);
            const data = await actionsApi.get(id);
            setAction(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    async function handleStatusChange(newStatus) {
        try {
            await actionsApi.updateStatus(id, newStatus);
            setAction({ ...action, status: newStatus });
        } catch (err) {
            console.error('Failed to update status:', err);
        }
    }

    function startEditing() {
        setEditForm({
            action_text: action.text || '',
            owner: action.owner || '',
            due_date: action.due_date || '',
            notes: action.notes || '',
        });
        setEditing(true);
    }

    async function handleSave(e) {
        e.preventDefault();
        try {
            setSaving(true);
            const updates = {};
            if (editForm.action_text !== action.text) updates.action_text = editForm.action_text;
            if (editForm.owner !== action.owner) updates.owner = editForm.owner;
            if (editForm.due_date !== (action.due_date || '')) updates.due_date = editForm.due_date || null;
            if (editForm.notes !== (action.notes || '')) updates.notes = editForm.notes || null;

            if (Object.keys(updates).length > 0) {
                await actionsApi.update(id, updates);
                await loadAction();
            }
            setEditing(false);
        } catch (err) {
            setError(err.message);
        } finally {
            setSaving(false);
        }
    }

    function formatDate(dateStr) {
        if (!dateStr) return '-';
        return new Date(dateStr).toLocaleDateString('en-NZ', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
        });
    }

    if (loading) {
        return (
            <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
            </div>
        );
    }

    if (error || !action) {
        return (
            <div className="card text-center py-12">
                <p className="text-red-600">{error || 'Action not found'}</p>
                <Link to="/actions" className="btn-primary mt-4 inline-block">
                    Back to Actions
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Back Link */}
            <Link to="/actions" className="text-brand-600 hover:text-brand-700 flex items-center gap-1">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back to Actions
            </Link>

            {editing ? (
                /* Edit Mode */
                <form onSubmit={handleSave} className="card">
                    <div className="flex items-center justify-between mb-4">
                        <h1 className="text-xl font-bold text-gray-900">Edit Action</h1>
                    </div>
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Action Text *</label>
                            <textarea
                                required
                                value={editForm.action_text}
                                onChange={(e) => setEditForm({ ...editForm, action_text: e.target.value })}
                                rows={3}
                                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2"
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Owner *</label>
                                <input
                                    type="text"
                                    required
                                    value={editForm.owner}
                                    onChange={(e) => setEditForm({ ...editForm, owner: e.target.value })}
                                    className="w-full rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Due Date</label>
                                <input
                                    type="date"
                                    value={editForm.due_date}
                                    onChange={(e) => setEditForm({ ...editForm, due_date: e.target.value })}
                                    className="w-full rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                            <textarea
                                value={editForm.notes}
                                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                                rows={3}
                                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2"
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
                /* View Mode */
                <>
                    <div className="card">
                        <div className="flex items-start justify-between mb-4">
                            <h1 className="text-xl font-bold text-gray-900">Action</h1>
                            <div className="flex items-center gap-2">
                                {permissions.can_write && (
                                    <button onClick={startEditing} className="btn-secondary text-sm">
                                        Edit
                                    </button>
                                )}
                                <span className={`px-3 py-1 text-sm rounded-full ${
                                    action.status === 'Complete'
                                        ? 'bg-green-100 text-green-800'
                                        : action.status === 'Parked'
                                            ? 'bg-yellow-100 text-yellow-800'
                                            : 'bg-blue-100 text-blue-800'
                                }`}>
                                    {action.status}
                                </span>
                            </div>
                        </div>
                        <p className="text-gray-800 text-lg whitespace-pre-wrap">{action.text}</p>
                    </div>

                    {action.notes && (
                        <div className="card">
                            <h2 className="text-lg font-semibold text-gray-900 mb-3">Notes</h2>
                            <p className="text-gray-700 whitespace-pre-wrap">{action.notes}</p>
                        </div>
                    )}

                    <div className="card">
                        <h2 className="text-lg font-semibold text-gray-900 mb-3">Details</h2>
                        <dl className="grid grid-cols-2 gap-4 mb-6">
                            <div>
                                <dt className="text-sm font-medium text-gray-500">Owner</dt>
                                <dd className="text-gray-900">{action.owner}</dd>
                            </div>
                            <div>
                                <dt className="text-sm font-medium text-gray-500">Due Date</dt>
                                <dd className="text-gray-900">{formatDate(action.due_date)}</dd>
                            </div>
                            {action.meeting_id && (
                                <div>
                                    <dt className="text-sm font-medium text-gray-500">Meeting</dt>
                                    <dd>
                                        <Link
                                            to={`/meetings/${action.meeting_id}`}
                                            className="text-brand-600 hover:text-brand-700"
                                        >
                                            View Meeting
                                        </Link>
                                    </dd>
                                </div>
                            )}
                        </dl>

                        {permissions.can_write && (
                            <div className="border-t pt-4">
                                <label className="block text-sm font-medium text-gray-700 mb-2">Update Status</label>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => handleStatusChange('Open')}
                                        className={`px-4 py-2 rounded-lg text-sm font-medium ${
                                            action.status === 'Open'
                                                ? 'bg-blue-600 text-white'
                                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                        }`}
                                    >
                                        Open
                                    </button>
                                    <button
                                        onClick={() => handleStatusChange('Complete')}
                                        className={`px-4 py-2 rounded-lg text-sm font-medium ${
                                            action.status === 'Complete'
                                                ? 'bg-green-600 text-white'
                                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                        }`}
                                    >
                                        Complete
                                    </button>
                                    <button
                                        onClick={() => handleStatusChange('Parked')}
                                        className={`px-4 py-2 rounded-lg text-sm font-medium ${
                                            action.status === 'Parked'
                                                ? 'bg-yellow-600 text-white'
                                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                        }`}
                                    >
                                        Parked
                                    </button>
                                </div>
                            </div>
                        )}

                        {permissions.is_chair_or_admin && (
                            <div className="border-t pt-4">
                                <button
                                    onClick={async () => {
                                        if (!confirm('Delete this action? This cannot be undone.')) return;
                                        try {
                                            await actionsApi.delete(id);
                                            navigate('/actions');
                                        } catch (err) {
                                            console.error('Delete failed:', err);
                                        }
                                    }}
                                    className="px-4 py-2 rounded-lg text-sm font-medium bg-red-50 text-red-700 hover:bg-red-100"
                                >
                                    Delete Action
                                </button>
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}

export default ActionDetail;

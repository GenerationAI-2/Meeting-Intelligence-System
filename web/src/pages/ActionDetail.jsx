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

            {/* Action Content */}
            <div className="card">
                <div className="flex items-start justify-between mb-4">
                    <h1 className="text-xl font-bold text-gray-900">Action</h1>
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
                <p className="text-gray-800 text-lg whitespace-pre-wrap">{action.text}</p>
            </div>

            {/* Notes */}
            {action.notes && (
                <div className="card">
                    <h2 className="text-lg font-semibold text-gray-900 mb-3">Notes</h2>
                    <p className="text-gray-700 whitespace-pre-wrap">{action.notes}</p>
                </div>
            )}

            {/* Details & Actions */}
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

                {/* Status Change — hidden for viewers */}
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

                {/* Delete — chairs and org admins only */}
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
        </div>
    );
}

export default ActionDetail;

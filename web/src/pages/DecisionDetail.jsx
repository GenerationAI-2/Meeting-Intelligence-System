import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { decisionsApi } from '../services/api';
import { useWorkspace } from '../contexts/WorkspaceContext';

function DecisionDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { permissions } = useWorkspace();
    const [decision, setDecision] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        loadDecision();
    }, [id]);

    async function loadDecision() {
        try {
            setLoading(true);
            const data = await decisionsApi.get(id);
            setDecision(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
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

    if (error || !decision) {
        return (
            <div className="card text-center py-12">
                <p className="text-red-600">{error || 'Decision not found'}</p>
                <Link to="/decisions" className="btn-primary mt-4 inline-block">
                    Back to Decisions
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Back Link */}
            <Link to="/decisions" className="text-brand-600 hover:text-brand-700 flex items-center gap-1">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back to Decisions
            </Link>

            {/* Decision Content */}
            <div className="card">
                <h1 className="text-xl font-bold text-gray-900 mb-4">Decision</h1>
                <p className="text-gray-800 text-lg whitespace-pre-wrap">{decision.text}</p>
            </div>

            {/* Context */}
            {decision.context && (
                <div className="card">
                    <h2 className="text-lg font-semibold text-gray-900 mb-3">Context</h2>
                    <p className="text-gray-700 whitespace-pre-wrap">{decision.context}</p>
                </div>
            )}

            {/* Metadata */}
            <div className="card">
                <h2 className="text-lg font-semibold text-gray-900 mb-3">Details</h2>
                <dl className="grid grid-cols-2 gap-4">
                    <div>
                        <dt className="text-sm font-medium text-gray-500">Meeting</dt>
                        <dd>
                            <Link
                                to={`/meetings/${decision.meeting_id}`}
                                className="text-brand-600 hover:text-brand-700"
                            >
                                {decision.meeting_title || 'View Meeting'}
                            </Link>
                        </dd>
                    </div>
                    <div>
                        <dt className="text-sm font-medium text-gray-500">Date</dt>
                        <dd className="text-gray-900">{formatDate(decision.created_at)}</dd>
                    </div>
                </dl>

                {/* Delete — chairs and org admins only */}
                {permissions.is_chair_or_admin && (
                    <div className="border-t pt-4 mt-4">
                        <button
                            onClick={async () => {
                                if (!confirm('Delete this decision? This cannot be undone.')) return;
                                try {
                                    await decisionsApi.delete(id);
                                    navigate('/decisions');
                                } catch (err) {
                                    console.error('Delete failed:', err);
                                }
                            }}
                            className="px-4 py-2 rounded-lg text-sm font-medium bg-red-50 text-red-700 hover:bg-red-100"
                        >
                            Delete Decision
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}

export default DecisionDetail;

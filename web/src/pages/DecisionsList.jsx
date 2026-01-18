import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { decisionsApi, meetingsApi } from '../services/api';

function DecisionsList() {
    const [decisions, setDecisions] = useState([]);
    const [meetings, setMeetings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [meetingFilter, setMeetingFilter] = useState('');
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const perPage = 50;

    useEffect(() => {
        loadMeetings();
    }, []);

    useEffect(() => {
        loadDecisions();
    }, [page, meetingFilter]);

    async function loadMeetings() {
        try {
            const data = await meetingsApi.list({ limit: 100 });
            setMeetings(data.meetings || []);
        } catch (err) {
            console.error('Failed to load meetings:', err);
        }
    }

    async function loadDecisions() {
        try {
            setLoading(true);
            const params = {
                limit: perPage,
                offset: (page - 1) * perPage
            };
            if (meetingFilter) params.meeting_id = meetingFilter;

            const data = await decisionsApi.list(params);
            setDecisions(data.decisions || []);
            setTotal(data.count || 0);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    function formatDate(dateStr) {
        if (!dateStr) return '-';
        return new Date(dateStr).toLocaleDateString('en-NZ', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
        });
    }

    if (loading && decisions.length === 0) {
        return (
            <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
            </div>
        );
    }

    return (
        <div>
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900">Decisions</h1>
                <p className="text-gray-600">Review decisions made in meetings</p>
            </div>

            {/* Filter */}
            <div className="card mb-6">
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Meeting</label>
                    <select
                        value={meetingFilter}
                        onChange={(e) => { setMeetingFilter(e.target.value); setPage(1); }}
                        className="rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 min-w-64"
                    >
                        <option value="">All Meetings</option>
                        {meetings.map((m) => (
                            <option key={m.id} value={m.id}>{m.title}</option>
                        ))}
                    </select>
                </div>
            </div>

            {error && (
                <div className="card text-center py-6 mb-6 bg-red-50 border-red-200">
                    <p className="text-red-600">{error}</p>
                </div>
            )}

            <div className="card overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="table-header">Decision</th>
                            <th className="table-header">Context</th>
                            <th className="table-header">Meeting</th>
                            <th className="table-header">Date</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {decisions.length === 0 ? (
                            <tr>
                                <td colSpan="4" className="table-cell text-center text-gray-500 py-8">
                                    No decisions found
                                </td>
                            </tr>
                        ) : (
                            decisions.map((decision) => (
                                <tr key={decision.id} className="hover:bg-gray-50">
                                    <td className="table-cell max-w-md">
                                        <p className="line-clamp-2">{decision.text}</p>
                                    </td>
                                    <td className="table-cell text-gray-500 max-w-xs">
                                        <p className="truncate">{decision.context || '-'}</p>
                                    </td>
                                    <td className="table-cell">
                                        <Link
                                            to={`/meetings/${decision.meeting_id}`}
                                            className="text-brand-600 hover:text-brand-700"
                                        >
                                            {decision.meeting_title}
                                        </Link>
                                    </td>
                                    <td className="table-cell text-gray-500">
                                        {formatDate(decision.created_at)}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>

                {/* Pagination */}
                {total > perPage && (
                    <div className="bg-gray-50 px-4 py-3 flex items-center justify-between border-t border-gray-200">
                        <div className="text-sm text-gray-700">
                            Showing {((page - 1) * perPage) + 1} to {Math.min(page * perPage, total)} of {total}
                        </div>
                        <div className="flex gap-2">
                            <button
                                onClick={() => setPage(p => Math.max(1, p - 1))}
                                disabled={page === 1}
                                className="btn-secondary disabled:opacity-50"
                            >
                                Previous
                            </button>
                            <button
                                onClick={() => setPage(p => p + 1)}
                                disabled={page * perPage >= total}
                                className="btn-secondary disabled:opacity-50"
                            >
                                Next
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default DecisionsList;

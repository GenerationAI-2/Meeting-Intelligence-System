import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { meetingsApi } from '../services/api';
import { useWorkspace } from '../contexts/WorkspaceContext';

function MeetingsList() {
    const { workspaceVersion } = useWorkspace();
    const [meetings, setMeetings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [searchQuery, setSearchQuery] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const perPage = 20;

    useEffect(() => {
        if (!isSearching) {
            loadMeetings();
        }
    }, [page, workspaceVersion]);

    async function loadMeetings() {
        try {
            setLoading(true);
            const data = await meetingsApi.list({
                limit: perPage,
                offset: (page - 1) * perPage
            });
            setMeetings(data.meetings || []);
            setTotal(data.count || 0);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    async function handleSearch(e) {
        e.preventDefault();
        const query = searchQuery.trim();
        if (!query) return;
        try {
            setLoading(true);
            setError(null);
            const data = await meetingsApi.search(query);
            setMeetings((data.results || []).map(r => ({
                id: r.id,
                title: r.title,
                date: r.date,
                attendees: r.attendees || null,
                source: r.source || null,
                snippet: r.snippet || null,
            })));
            setTotal(data.count || 0);
            setIsSearching(true);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    function clearSearch() {
        setSearchQuery('');
        setIsSearching(false);
        setPage(1);
        loadMeetings();
    }

    function formatDate(dateStr) {
        if (!dateStr) return '-';
        return new Date(dateStr).toLocaleDateString('en-NZ', {
            day: 'numeric',
            month: 'short',
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

    if (error) {
        return (
            <div className="card text-center py-12">
                <p className="text-red-600">{error}</p>
                <button onClick={loadMeetings} className="btn-primary mt-4">
                    Retry
                </button>
            </div>
        );
    }

    return (
        <div>
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900">Meetings</h1>
                <p className="text-gray-600">Browse and view meeting transcripts</p>
            </div>

            {/* Search */}
            <form onSubmit={handleSearch} className="card mb-6">
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search meetings by keyword..."
                        className="flex-1 rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500"
                    />
                    <button type="submit" className="btn-primary">
                        Search
                    </button>
                    {isSearching && (
                        <button type="button" onClick={clearSearch} className="btn-secondary">
                            Clear
                        </button>
                    )}
                </div>
                {isSearching && (
                    <p className="text-sm text-gray-500 mt-2">
                        {total} result{total !== 1 ? 's' : ''} for "{searchQuery}"
                    </p>
                )}
            </form>

            <div className="card overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="table-header">Title</th>
                            <th className="table-header">Date</th>
                            <th className="table-header">Attendees</th>
                            <th className="table-header">Source</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {meetings.length === 0 ? (
                            <tr>
                                <td colSpan="4" className="table-cell text-center text-gray-500 py-8">
                                    No meetings found
                                </td>
                            </tr>
                        ) : (
                            meetings.map((meeting) => (
                                <tr
                                    key={meeting.id}
                                    className="hover:bg-gray-50 cursor-pointer"
                                    onClick={() => window.location.href = `/meetings/${meeting.id}`}
                                >
                                    <td className="table-cell">
                                        <Link
                                            to={`/meetings/${meeting.id}`}
                                            className="text-brand-600 hover:text-brand-700 font-medium"
                                        >
                                            {meeting.title}
                                        </Link>
                                        {meeting.snippet && (
                                            <p className="text-sm text-gray-500 mt-1 line-clamp-2">{meeting.snippet}</p>
                                        )}
                                    </td>
                                    <td className="table-cell text-gray-500">
                                        {formatDate(meeting.date)}
                                    </td>
                                    <td className="table-cell text-gray-500">
                                        {meeting.attendees || '-'}
                                    </td>
                                    <td className="table-cell">
                                        {meeting.source ? (
                                            <span className={`px-2 py-1 text-xs rounded-full ${meeting.source === 'Fireflies'
                                                    ? 'bg-purple-100 text-purple-800'
                                                    : 'bg-gray-100 text-gray-800'
                                                }`}>
                                                {meeting.source}
                                            </span>
                                        ) : '-'}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>

                {/* Pagination */}
                {!isSearching && total > perPage && (
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

export default MeetingsList;

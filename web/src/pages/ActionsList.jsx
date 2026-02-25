import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { actionsApi } from '../services/api';
import { useWorkspace } from '../contexts/WorkspaceContext';

function ActionsList() {
    const { permissions } = useWorkspace();
    const [actions, setActions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [statusFilter, setStatusFilter] = useState('Open');
    const [ownerFilter, setOwnerFilter] = useState('');
    const [owners, setOwners] = useState([]);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [sortColumn, setSortColumn] = useState(null);
    const [sortDirection, setSortDirection] = useState(null);
    const perPage = 50;

    useEffect(() => {
        actionsApi.owners().then(data => setOwners(data.owners || [])).catch(() => {});
    }, []);

    useEffect(() => {
        loadActions();
    }, [page, statusFilter, ownerFilter]);

    async function loadActions() {
        try {
            setLoading(true);
            const params = {
                limit: perPage,
                offset: (page - 1) * perPage
            };
            if (statusFilter && statusFilter !== 'All') params.status = statusFilter;
            if (ownerFilter) params.owner = ownerFilter;

            const data = await actionsApi.list(params);
            setActions(data.actions || []);
            setTotal(data.count || 0);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    async function handleStatusChange(actionId, newStatus) {
        try {
            await actionsApi.updateStatus(actionId, newStatus);
            setActions(actions.map(a =>
                a.id === actionId ? { ...a, status: newStatus } : a
            ));
        } catch (err) {
            console.error('Failed to update status:', err);
        }
    }

    function handleSort(column) {
        if (sortColumn !== column) {
            setSortColumn(column);
            setSortDirection('asc');
        } else if (sortDirection === 'asc') {
            setSortDirection('desc');
        } else {
            setSortColumn(null);
            setSortDirection(null);
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

    const sortedActions = [...actions];
    if (sortColumn) {
        sortedActions.sort((a, b) => {
            let aVal = a[sortColumn];
            let bVal = b[sortColumn];
            if (aVal == null && bVal == null) return 0;
            if (aVal == null) return 1;
            if (bVal == null) return -1;
            if (sortColumn === 'due_date') {
                aVal = new Date(aVal);
                bVal = new Date(bVal);
            } else {
                aVal = aVal.toLowerCase();
                bVal = bVal.toLowerCase();
            }
            if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
            return 0;
        });
    }

    if (loading && actions.length === 0) {
        return (
            <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
            </div>
        );
    }

    return (
        <div>
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900">Actions</h1>
                <p className="text-gray-600">Track and manage action items</p>
            </div>

            {/* Filters */}
            <div className="card mb-6">
                <div className="flex flex-wrap gap-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                        <select
                            value={statusFilter}
                            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
                            className="rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2"
                        >
                            <option value="All">All</option>
                            <option value="Open">Open</option>
                            <option value="Complete">Complete</option>
                            <option value="Parked">Parked</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Owner</label>
                        <select
                            value={ownerFilter}
                            onChange={(e) => { setOwnerFilter(e.target.value); setPage(1); }}
                            className="rounded-lg border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2"
                        >
                            <option value="">All owners</option>
                            {owners.map((owner) => (
                                <option key={owner} value={owner}>{owner}</option>
                            ))}
                        </select>
                    </div>
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
                            <th className="table-header">Action</th>
                            <th className="table-header cursor-pointer select-none" onClick={() => handleSort('owner')}>
                                Owner {sortColumn === 'owner' && (sortDirection === 'asc' ? '\u25B2' : '\u25BC')}
                            </th>
                            <th className="table-header cursor-pointer select-none" onClick={() => handleSort('due_date')}>
                                Due Date {sortColumn === 'due_date' && (sortDirection === 'asc' ? '\u25B2' : '\u25BC')}
                            </th>
                            <th className="table-header cursor-pointer select-none" onClick={() => handleSort('status')}>
                                Status {sortColumn === 'status' && (sortDirection === 'asc' ? '\u25B2' : '\u25BC')}
                            </th>
                            <th className="table-header">Meeting</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {sortedActions.length === 0 ? (
                            <tr>
                                <td colSpan="5" className="table-cell text-center text-gray-500 py-8">
                                    No actions found
                                </td>
                            </tr>
                        ) : (
                            sortedActions.map((action) => (
                                <tr
                                    key={action.id}
                                    className="hover:bg-gray-50 cursor-pointer"
                                    onClick={() => window.location.href = `/actions/${action.id}`}
                                >
                                    <td className="table-cell max-w-md">
                                        <p className="line-clamp-2 text-brand-600 hover:text-brand-700">{action.text}</p>
                                    </td>
                                    <td className="table-cell text-gray-500">
                                        {action.owner}
                                    </td>
                                    <td className="table-cell text-gray-500">
                                        {formatDate(action.due_date)}
                                    </td>
                                    <td className="table-cell">
                                        {permissions.can_write ? (
                                            <select
                                                value={action.status}
                                                onChange={(e) => {
                                                    e.stopPropagation();
                                                    handleStatusChange(action.id, e.target.value);
                                                }}
                                                onClick={(e) => e.stopPropagation()}
                                                className={`rounded px-2 py-1 text-sm border-0 cursor-pointer ${action.status === 'Complete'
                                                        ? 'bg-green-100 text-green-800'
                                                        : action.status === 'Parked'
                                                            ? 'bg-yellow-100 text-yellow-800'
                                                            : 'bg-blue-100 text-blue-800'
                                                    }`}
                                            >
                                                <option value="Open">Open</option>
                                                <option value="Complete">Complete</option>
                                                <option value="Parked">Parked</option>
                                            </select>
                                        ) : (
                                            <span className={`rounded px-2 py-1 text-sm ${action.status === 'Complete'
                                                    ? 'bg-green-100 text-green-800'
                                                    : action.status === 'Parked'
                                                        ? 'bg-yellow-100 text-yellow-800'
                                                        : 'bg-blue-100 text-blue-800'
                                                }`}>
                                                {action.status}
                                            </span>
                                        )}
                                    </td>
                                    <td className="table-cell">
                                        {action.meeting_id ? (
                                            <Link
                                                to={`/meetings/${action.meeting_id}`}
                                                className="text-brand-600 hover:text-brand-700"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                View Meeting
                                            </Link>
                                        ) : '-'}
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

export default ActionsList;

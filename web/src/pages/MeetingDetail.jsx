import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { meetingsApi } from '../services/api';

function MeetingDetail() {
    const { id } = useParams();
    const [meeting, setMeeting] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [transcriptExpanded, setTranscriptExpanded] = useState(false);

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

            {/* Header */}
            <div className="card">
                <div className="flex items-start justify-between">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">{meeting.title}</h1>
                        <p className="text-gray-500 mt-1">{formatDate(meeting.date)}</p>
                    </div>
                    <span className={`px-3 py-1 text-sm rounded-full ${meeting.source === 'Fireflies'
                            ? 'bg-purple-100 text-purple-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                        {meeting.source}
                    </span>
                </div>

                {meeting.attendees && (
                    <div className="mt-4">
                        <h3 className="text-sm font-medium text-gray-500">Attendees</h3>
                        <p className="text-gray-900">{meeting.attendees}</p>
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
                                <span className={`px-2 py-1 text-xs rounded-full ${action.status === 'Complete'
                                        ? 'bg-green-100 text-green-800'
                                        : action.status === 'Parked'
                                            ? 'bg-yellow-100 text-yellow-800'
                                            : 'bg-blue-100 text-blue-800'
                                    }`}>
                                    {action.status}
                                </span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

export default MeetingDetail;

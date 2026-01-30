import { useMsal, useIsAuthenticated } from '@azure/msal-react';
import { Navigate } from 'react-router-dom';
import { loginRequest } from '../authConfig';

function Login() {
    const { instance } = useMsal();
    const isAuthenticated = useIsAuthenticated();

    const handleLogin = () => {
        instance.loginRedirect(loginRequest);
    };

    if (isAuthenticated) {
        return <Navigate to="/meetings" replace />;
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 to-brand-100">
            <div className="max-w-md w-full mx-4">
                <div className="card text-center">
                    <h1 className="text-3xl font-bold text-gray-900 mb-2">Meeting Intelligence</h1>
                    <p className="text-gray-600 mb-8">
                        Access meeting transcripts, action items, and decisions.
                    </p>
                    <button
                        onClick={handleLogin}
                        className="btn-primary w-full flex items-center justify-center gap-2"
                    >
                        <svg className="w-5 h-5" viewBox="0 0 21 21" xmlns="http://www.w3.org/2000/svg">
                            <rect x="1" y="1" width="9" height="9" fill="#f25022" />
                            <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
                            <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
                            <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
                        </svg>
                        Sign in with Microsoft
                    </button>
                </div>
            </div>
        </div>
    );
}

export default Login;

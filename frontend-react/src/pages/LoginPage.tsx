import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Link2 } from 'lucide-react';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center mb-8">
          <Link2 className="w-8 h-8 text-pink-500" />
          <span className="ml-3 text-2xl font-bold text-white">BackVora</span>
        </div>
        <form onSubmit={handleSubmit} className="bg-gray-800 rounded-lg p-6 space-y-4 border border-gray-700">
          <h2 className="text-lg font-semibold text-white text-center">Sign In</h2>
          {error && <div className="text-red-400 text-sm text-center">{error}</div>}
          <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} required
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-pink-500" />
          <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-pink-500" />
          <button type="submit" disabled={loading}
            className="w-full py-2 bg-pink-600 hover:bg-pink-700 disabled:opacity-50 text-white rounded font-medium transition-colors">
            {loading ? '...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}

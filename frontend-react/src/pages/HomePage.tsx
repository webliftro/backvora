import { Link } from 'react-router-dom';
import { Link2, TrendingUp, Globe, BarChart3, ArrowRight } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

export default function HomePage() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col">
      {/* Nav */}
      <nav className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center">
          <Link2 className="w-5 h-5 text-pink-500" />
          <span className="ml-2 text-lg font-semibold text-white">BackVora</span>
        </div>
        <div>
          {user ? (
            <Link
              to="/domains"
              className="px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-md text-sm font-medium transition-colors"
            >
              Go to Dashboard
            </Link>
          ) : (
            <Link
              to="/login"
              className="px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-md text-sm font-medium transition-colors"
            >
              Sign In
            </Link>
          )}
        </div>
      </nav>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 text-center">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center justify-center mb-6">
            <div className="bg-pink-500/10 border border-pink-500/20 rounded-full p-4">
              <Link2 className="w-10 h-10 text-pink-500" />
            </div>
          </div>

          <h1 className="text-5xl sm:text-6xl font-bold text-white mb-4 tracking-tight">
            Back<span className="text-pink-500">Vora</span>
          </h1>

          <p className="text-xl text-gray-400 mb-3 font-medium">
            Link Building Intelligence
          </p>

          <p className="text-gray-500 max-w-xl mx-auto mb-10 leading-relaxed">
            Track domains, manage outreach, and close deals — all in one place.
            BackVora gives you the tools to build high-quality backlinks at scale.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            {user ? (
              <Link
                to="/domains"
                className="inline-flex items-center px-6 py-3 bg-pink-600 hover:bg-pink-700 text-white rounded-lg font-medium transition-colors text-sm"
              >
                Go to Dashboard
                <ArrowRight className="ml-2 w-4 h-4" />
              </Link>
            ) : (
              <Link
                to="/login"
                className="inline-flex items-center px-6 py-3 bg-pink-600 hover:bg-pink-700 text-white rounded-lg font-medium transition-colors text-sm"
              >
                Get Started
                <ArrowRight className="ml-2 w-4 h-4" />
              </Link>
            )}
          </div>
        </div>

        {/* Feature highlights */}
        <div className="mt-20 grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-3xl w-full px-4">
          {[
            {
              icon: <Globe className="w-5 h-5 text-pink-500" />,
              title: 'Domain Tracking',
              desc: 'Monitor prospective domains, DR scores, and contact info in one place.',
            },
            {
              icon: <TrendingUp className="w-5 h-5 text-pink-500" />,
              title: 'Outreach Pipeline',
              desc: 'Manage your link building campaigns from first contact to published link.',
            },
            {
              icon: <BarChart3 className="w-5 h-5 text-pink-500" />,
              title: 'Deal Management',
              desc: 'Track prices, negotiations, and deal status across all your partners.',
            },
          ].map((f) => (
            <div
              key={f.title}
              className="bg-gray-800/50 border border-gray-700 rounded-xl p-5 text-left"
            >
              <div className="mb-3">{f.icon}</div>
              <h3 className="text-white font-semibold text-sm mb-1">{f.title}</h3>
              <p className="text-gray-500 text-xs leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 px-6 py-4 text-center text-xs text-gray-600">
        © {new Date().getFullYear()} BackVora. All rights reserved.
      </footer>
    </div>
  );
}

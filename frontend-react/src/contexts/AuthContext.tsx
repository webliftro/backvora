import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

interface User { id: string; email: string; name: string | null; is_active: boolean }
interface AuthCtx {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(AuthContext);

const B = '/api/v1/auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);

  const fetchMe = async (t: string) => {
    try {
      const r = await fetch(`${B}/me`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) { setUser(await r.json()); return true; }
      // Try refresh
      const rt = localStorage.getItem('refresh_token');
      if (rt) {
        const rr = await fetch(`${B}/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: rt }) });
        if (rr.ok) {
          const data = await rr.json();
          localStorage.setItem('token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token);
          setToken(data.access_token);
          const mr = await fetch(`${B}/me`, { headers: { Authorization: `Bearer ${data.access_token}` } });
          if (mr.ok) { setUser(await mr.json()); return true; }
        }
      }
    } catch {}
    logout();
    return false;
  };

  useEffect(() => {
    if (token) fetchMe(token).finally(() => setLoading(false));
    else setLoading(false);
  }, []);

  const login = async (email: string, password: string) => {
    const r = await fetch(`${B}/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Login failed'); }
    const data = await r.json();
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    setToken(data.access_token);
    await fetchMe(data.access_token);
  };

  const register = async (email: string, password: string, name?: string) => {
    const r = await fetch(`${B}/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password, name }) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Registration failed'); }
    await login(email, password);
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    setToken(null);
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>{children}</AuthContext.Provider>;
}

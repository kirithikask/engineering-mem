import React, { createContext, useContext, useState, useCallback } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

const readStoredUser = () => {
  try {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

export const AuthProvider = ({ children }) => {
  // No implicit/demo session: an operator is only present if they signed in.
  const [user, setUser] = useState(readStoredUser);
  const [token, setToken] = useState(() => localStorage.getItem('token'));

  const persist = (nextUser, nextToken) => {
    setUser(nextUser);
    setToken(nextToken);
    localStorage.setItem('user', JSON.stringify(nextUser));
    localStorage.setItem('token', nextToken);
  };

  const login = useCallback(async (username, password) => {
    // Credentials are verified only by the backend. There is deliberately no
    // client-side fallback that would admit an operator the API rejected.
    const res = await api.post('/auth/login', { username, password });
    persist(res.user, res.access_token);
    return res.user;
  }, []);

  const signup = useCallback(async ({ fullName, email, username, password, role }) => {
    const res = await api.post('/auth/signup', {
      full_name: fullName,
      email,
      username,
      password,
      role,
    });
    persist(res.user, res.access_token);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('user');
    localStorage.removeItem('token');
  }, []);

  const role = user?.role || null;

  return (
    <AuthContext.Provider value={{ user, token, role, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);

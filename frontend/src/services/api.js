import axios from 'axios';

const API_BASE_URL = `${import.meta.env.BASE_URL}api`;

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ============================================================================
// Authentication API
// ============================================================================

export const login = async (email) => {
  const response = await api.post('/auth/login', { email });
  return response.data;
};

export const logout = async (sessionToken) => {
  const response = await api.post('/auth/logout', null, {
    params: { session_token: sessionToken }
  });
  return response.data;
};

export const verifySession = async (sessionToken) => {
  const response = await api.get(`/auth/session/${sessionToken}`);
  return response.data;
};

// ============================================================================
// Synthesis API
// ============================================================================

export const getSynthesisFields = async () => {
  const response = await api.get('/synthesis/fields');
  return response.data;
};

export const uploadSynthesisData = async (uploadData) => {
  const response = await api.post('/synthesis/upload', uploadData);
  return response.data;
};

export default api;

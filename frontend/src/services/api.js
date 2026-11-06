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

// ============================================================================
// Fabrication Traveler API
// ============================================================================

export const getFabTemplates = async () => (await api.get('/fab/templates')).data;

export const listWafers = async (project) =>
  (await api.get('/fab/wafers', { params: { project } })).data;

export const createWafer = async (body) => (await api.post('/fab/wafers', body)).data;

export const getTraveler = async (waferId) =>
  (await api.get(`/fab/wafers/${encodeURIComponent(waferId)}/traveler`)).data;

export const recordStep = async (body) => (await api.post('/fab/steps', body)).data;

export const listPrinters = async () => (await api.get('/fab/printers')).data;

export const printCrucibleLabel = async (printerId, sampleId) =>
  (await api.post('/fab/print', { printer_id: printerId, sample_id: sampleId })).data;

export default api;

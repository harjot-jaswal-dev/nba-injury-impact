import axios from 'axios'

const api = axios.create({
  baseURL: (import.meta.env.VITE_API_URL || '') + '/api',
  withCredentials: true,
  timeout: 30000,
})

// Games & Predictions
export const getUpcomingGames = (limit = 15) =>
  api.get('/games/upcoming', { params: { limit } }).then(r => r.data)

export const getPredictions = (gameId, { signal } = {}) =>
  api.get(`/predictions/${gameId}`, { signal }).then(r => r.data)

export const getRipple = (gameId, team, absentPlayerIds, { signal } = {}) =>
  api.get(`/predictions/${gameId}/ripple`, {
    signal,
    params: {
      ...(team && { team }),
      ...(absentPlayerIds?.length && { absent_player_ids: absentPlayerIds.join(',') }),
    },
  }).then(r => r.data)

// Simulate
export const simulate = (body) =>
  api.post('/simulate', body).then(r => r.data)

// Players & Teams
export const getPlayers = ({ team, search } = {}) =>
  api.get('/players', { params: { team, search } }).then(r => r.data)

export const getPlayer = (playerId) =>
  api.get(`/players/${playerId}`).then(r => r.data)

export const getTeams = () =>
  api.get('/teams').then(r => r.data)

// Chat
export const sendChat = (message) =>
  api.post('/chat', { message }).then(r => r.data)

export const getChatExamples = () =>
  api.get('/chat/examples').then(r => r.data)

// Auth
export const getAuthUrl = () =>
  api.get('/auth/google').then(r => r.data)

export const getMe = () =>
  api.get('/auth/me').then(r => r.data)

export const logout = () =>
  api.post('/auth/logout').then(r => r.data)

export default api

import axios from 'axios'
import { useAuthStore } from '../store/auth'

const api = axios.create({
  baseURL: '/api/v1',
})

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Auth API
export const authApi = {
  login: async (email: string, password: string) => {
    const response = await api.post('/auth/login', { email, password })
    return response.data
  },
  register: async (email: string, password: string) => {
    const response = await api.post('/auth/register', { email, password })
    return response.data
  },
  getMe: async () => {
    const response = await api.get('/auth/me')
    return response.data
  },
  getUsers: async () => {
    const response = await api.get('/auth/users')
    return response.data
  },
  updateUser: async (userId: string, data: { role?: string; is_active?: boolean }) => {
    const response = await api.patch(`/auth/users/${userId}`, data)
    return response.data
  },
}

// Cities API
export const citiesApi = {
  resolve: async (city: string, state: string) =>
    api.get('/cities/resolve', { params: { city, state } }).then(r => r.data),
  candidates: async (city: string, state: string) =>
    api.get('/cities/candidates', { params: { city, state } }).then(r => r.data),
}

// Projects API
export const projectsApi = {
  list: async (status?: string) => {
    const params = status ? { status } : {}
    const response = await api.get('/projects', { params })
    return response.data
  },
  get: async (id: string) => {
    const response = await api.get(`/projects/${id}`)
    return response.data
  },
  create: async (data: {
    name: string
    description?: string
    bounds?: { min_lat: number; min_lng: number; max_lat: number; max_lng: number }
    bounds_polygon?: object
  }) => {
    const response = await api.post('/projects', data)
    return response.data
  },
  update: async (id: string, data: { name?: string; description?: string; status?: string }) => {
    const response = await api.patch(`/projects/${id}`, data)
    return response.data
  },
  delete: async (id: string) => {
    const response = await api.delete(`/projects/${id}`)
    return response.data
  },
}

// Polygons API
export const polygonsApi = {
  getForProject: async (projectId: string) => {
    const response = await api.get(`/polygons/project/${projectId}`)
    return response.data
  },
  create: async (projectId: string, geometry: object, properties?: object) => {
    const response = await api.post(`/polygons/project/${projectId}`, {
      geometry,
      properties: properties || {},
    })
    return response.data
  },
  update: async (polygonId: string, data: { geometry?: object; properties?: object; status?: string }) => {
    const response = await api.patch(`/polygons/${polygonId}`, data)
    return response.data
  },
  delete: async (polygonId: string) => {
    const response = await api.delete(`/polygons/${polygonId}`)
    return response.data
  },
  split: async (polygonId: string, lineStart: [number, number], lineEnd: [number, number]) => {
    const response = await api.post(`/polygons/${polygonId}/split`, {
      line_start: lineStart,
      line_end: lineEnd,
    })
    return response.data
  },
}

// Maps API
export const mapsApi = {
  getTileUrl: async (): Promise<string> => {
    const response = await api.get('/maps/tile-url')
    return response.data.url
  },
}

// Inference API
export const inferenceApi = {
  run: async (projectId: string) => {
    const response = await api.post(`/inference/run/${projectId}`)
    return response.data
  },
  status: async (projectId: string) => {
    const response = await api.get(`/inference/status/${projectId}`)
    return response.data
  },
}

export const inferenceStreamUrl = (projectId: string, token: string) =>
  `/api/v1/inference/stream/${projectId}?token=${encodeURIComponent(token)}`

export const citySearchStreamUrl = (city: string, state: string, token: string) =>
  `/api/v1/cities/search/stream?city=${encodeURIComponent(city)}&state=${encodeURIComponent(state)}&token=${encodeURIComponent(token)}`

export default api

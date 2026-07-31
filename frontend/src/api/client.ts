import axios from 'axios'
import type { Dashboard, Interaction, Scan, Settings, Suggestion, SuggestionStatus, User } from '@/types'

const client = axios.create({ baseURL: '/api/v1', timeout: 30000 })

export const api = {
  dashboard: () => client.get<Dashboard>('/dashboard').then(r => r.data),
  users: () => client.get<User[]>('/users').then(r => r.data),
  createUser: (data: Pick<User, 'nickname' | 'relationship' | 'priority' | 'tags'>) => client.post<User>('/users', data).then(r => r.data),
  updateUser: (id: number, data: Partial<User>) => client.patch<User>(`/users/${id}`, data).then(r => r.data),
  deleteUser: (id: number) => client.delete(`/users/${id}`),
  interactions: (id: number) => client.get<Interaction[]>(`/users/${id}/interactions`).then(r => r.data),
  suggestions: () => client.get<Suggestion[]>('/suggestions').then(r => r.data),
  updateSuggestion: (id: number, status: SuggestionStatus) => client.patch<Suggestion>(`/suggestions/${id}`, { status }).then(r => r.data),
  scans: () => client.get<Scan[]>('/scans').then(r => r.data),
  scan: (dry_run = false) => client.post<Scan>('/scans', { dry_run }).then(r => r.data),
  settings: () => client.get<Settings>('/settings').then(r => r.data),
  updateSettings: (data: Partial<Settings>) => client.put<Settings>('/settings', data).then(r => r.data),
}


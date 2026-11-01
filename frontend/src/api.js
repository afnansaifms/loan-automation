import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
export const api = axios.create({ baseURL: API_BASE })

export const listApplications = () => api.get('/applications/')
export const getApplication = (id) => api.get(`/applications/${id}`)
export const createApplication = (name) =>
  api.post('/applications/', null, { params: { applicant_name: name } })
export const deleteApplication = (id) => api.delete(`/applications/${id}`)

export const uploadStatement = (applicationId, file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post(`/applications/${applicationId}/statements`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
export const processStatement = (statementId) =>
  api.post(`/applications/statements/${statementId}/process`)
export const getLatestStatement = (id) => api.get(`/applications/${id}/statements/latest`)

export const uploadDocument = (applicationId, file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post(`/applications/${applicationId}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
export const processDocument = (documentId) =>
  api.post(`/applications/documents/${documentId}/process`)
export const listDocuments = (id) => api.get(`/applications/${id}/documents`)

export const verifyApplication = (id) => api.get(`/applications/${id}/verify`)
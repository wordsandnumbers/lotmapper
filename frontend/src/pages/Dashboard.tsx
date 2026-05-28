import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { projectsApi } from '../services/api'
import CreateProjectModal from '../components/CreateProjectModal'

interface Project {
  id: string
  name: string
  description: string | null
  status: string
  polygon_count: number
  created_at: string
}

export default function Dashboard() {
  const PAGE_SIZE = 10

  const [projects, setProjects] = useState<Project[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const navigate = useNavigate()

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const loadProjects = async (currentPage = page) => {
    try {
      const data = await projectsApi.list(statusFilter || undefined, currentPage, PAGE_SIZE)
      setProjects(data.projects)
      setTotal(data.total)
    } catch (error) {
      console.error('Failed to load projects:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProjects(page)
    window.scrollTo(0, 0)
  }, [page, statusFilter])

  const handleProjectCreated = () => {
    setShowCreateModal(false)
    loadProjects()
  }

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'pending':
        return 'bg-gray-100 text-gray-800'
      case 'processing':
        return 'bg-yellow-100 text-yellow-800'
      case 'review':
        return 'bg-brand-primary/10 text-brand-primary'
      case 'approved':
        return 'bg-green-100 text-green-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-app-heading">Projects</h1>
            <p className="mt-1 text-sm text-app-body">Review detection projects and parking lot boundaries.</p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="bg-brand-primary hover:bg-brand-primaryHover text-white px-4 py-2 rounded-md text-sm font-medium shadow-sm"
          >
            New Project
          </button>
        </div>

        <div className="mb-4">
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
            className="border border-black/10 bg-white rounded-md px-3 py-2 text-sm shadow-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/25"
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="processing">Processing</option>
            <option value="review">Review</option>
            <option value="approved">Approved</option>
          </select>
        </div>

        {loading ? (
          <div className="text-center py-12 text-app-body">Loading...</div>
        ) : projects.length === 0 ? (
          <div className="text-center py-12 bg-white/95 rounded-lg border border-black/10 shadow-sm">
            <p className="text-app-body">No projects yet. Create one to get started!</p>
          </div>
        ) : (
          <>
            <div className="bg-white/95 shadow-sm ring-1 ring-black/10 overflow-hidden sm:rounded-md">
              <ul className="divide-y divide-gray-200">
                {projects.map((project) => (
                  <li key={project.id}>
                    <div className="flex items-center hover:bg-brand-primary/5">
                      <button
                        onClick={() => navigate(`/project/${project.id}`)}
                        className="flex-1 text-left"
                      >
                        <div className="px-4 py-4 sm:px-6">
                          <div className="flex items-center justify-between">
                            <p className="text-sm font-medium text-brand-primary truncate">
                              {project.name}
                            </p>
                            <div className="ml-2 flex-shrink-0 flex">
                              <span
                                className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusBadgeClass(
                                  project.status
                                )}`}
                              >
                                {project.status}
                              </span>
                            </div>
                          </div>
                          <div className="mt-2 sm:flex sm:justify-between">
                            <div className="sm:flex">
                              <p className="flex items-center text-sm text-app-body">
                                {project.description || 'No description'}
                              </p>
                            </div>
                            <div className="mt-2 flex items-center text-sm text-app-body sm:mt-0">
                              <span>{project.polygon_count} polygons</span>
                              <span className="mx-2">|</span>
                              <span>
                                {new Date(project.created_at).toLocaleDateString()}
                              </span>
                            </div>
                          </div>
                        </div>
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <p className="text-sm text-app-body">
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => p - 1)}
                  disabled={page === 1}
                  className="px-3 py-1 text-sm border border-black/10 bg-white rounded-md disabled:opacity-40 hover:bg-brand-primary/5"
                >
                  Previous
                </button>
                <span className="px-3 py-1 text-sm text-app-body">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page === totalPages}
                  className="px-3 py-1 text-sm border border-black/10 bg-white rounded-md disabled:opacity-40 hover:bg-brand-primary/5"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {showCreateModal && (
        <CreateProjectModal
          onClose={() => setShowCreateModal(false)}
          onCreated={handleProjectCreated}
        />
      )}
    </div>
  )
}

import { Outlet, Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? 'border-blue-500 text-gray-900 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium'
    : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium'

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <nav className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              <div className="flex-shrink-0 flex items-center">
                <Link to="/dashboard">
                  <div className="w-8 h-8 bg-blue-600 rounded-md flex items-center justify-center">
                    <span className="text-white font-bold text-lg leading-none">P</span>
                  </div>
                </Link>
              </div>
              <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                <NavLink to="/dashboard" className={navLinkClass}>
                  Dashboard
                </NavLink>
                {user?.role === 'admin' && (
                  <NavLink to="/admin" className={navLinkClass}>
                    Admin
                  </NavLink>
                )}
              </div>
            </div>
            <div className="flex items-center">
              <span className="hidden sm:block text-sm text-gray-500 mr-4">
                {user?.email} ({user?.role})
              </span>
              <button
                onClick={handleLogout}
                className="bg-gray-200 hover:bg-gray-300 text-gray-700 px-3 py-2 rounded-md text-sm font-medium"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main>
        <Outlet />
      </main>
    </div>
  )
}

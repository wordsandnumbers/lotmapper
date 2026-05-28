import { Outlet, Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? 'border-brand-accent text-app-heading inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium'
    : 'border-transparent text-app-body hover:border-brand-primary hover:text-app-heading inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium'

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-app-canvas text-app-heading">
      <nav className="border-b border-black/10 bg-app-panel/95 shadow-sm backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              <div className="flex-shrink-0 flex items-center">
                <Link to="/dashboard">
                  <div className="w-8 h-8 bg-brand-primary rounded-md flex items-center justify-center ring-1 ring-brand-accent/30">
                    <span className="text-white font-bold text-sm leading-none">LM</span>
                  </div>
                </Link>
              </div>
              <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                <NavLink to="/dashboard" className={navLinkClass}>
                  Dashboard
                </NavLink>
                {(user?.role === 'admin' || user?.role === 'owner') && (
                  <NavLink to="/admin" className={navLinkClass}>
                    Admin
                  </NavLink>
                )}
              </div>
            </div>
            <div className="flex items-center">
              <span className="hidden sm:block text-sm text-app-body mr-4">
                {user?.email} ({user?.role})
              </span>
              <button
                onClick={handleLogout}
                className="bg-brand-primary/10 hover:bg-brand-primary/15 text-brand-primary px-3 py-2 rounded-md text-sm font-medium"
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

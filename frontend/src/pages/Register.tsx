import { useState } from 'react'
import { Link } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import { authApi } from '../services/api'

export default function Register() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await authApi.requestAccess(email)
      setSuccess(true)
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <AuthLayout title="Request submitted" subtitle="Your access request is queued for review.">
        <div className="rounded border border-green-300 bg-green-50 px-4 py-3 text-green-800">
          <h2 className="font-bold">Request submitted</h2>
          <p className="mt-2">
            An owner will review your request and email you when approved.
          </p>
        </div>
        <div className="mt-6 text-center text-sm">
          <Link to="/login" className="font-medium text-brand-primary hover:text-brand-primaryHover">
            Back to sign in
          </Link>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Request access" subtitle="Enter your email to request a LotMapper account.">
      <form className="space-y-4" onSubmit={handleSubmit}>
        {error && (
          <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-red-700">
            {error}
          </div>
        )}
        <div>
          <label htmlFor="email" className="sr-only">
            Email address
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            className="block w-full rounded-md border border-gray-300 px-3 py-2.5 text-gray-950 placeholder-gray-500 shadow-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/25 sm:text-sm"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="flex w-full justify-center rounded-md border border-transparent bg-brand-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-primaryHover focus:outline-none focus:ring-2 focus:ring-brand-accent focus:ring-offset-2 disabled:opacity-50"
        >
          {loading ? 'Submitting…' : 'Request access'}
        </button>

        <div className="text-center text-sm">
          <Link to="/login" className="font-medium text-brand-primary hover:text-brand-primaryHover">
            Already have an account? Sign in
          </Link>
        </div>
      </form>
    </AuthLayout>
  )
}

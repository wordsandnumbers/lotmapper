import { useEffect, type ReactNode } from 'react'

type AuthLayoutProps = {
  title: string
  subtitle?: string
  children: ReactNode
}

export default function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  useEffect(() => {
    document.body.classList.add('auth-route')
    return () => document.body.classList.remove('auth-route')
  }, [])

  return (
    <div className="min-h-screen overflow-hidden bg-auth-canvas text-auth-logo">
      <div className="relative flex min-h-screen items-center justify-center px-4 py-10 sm:px-6 lg:px-8">
        <div className="auth-map-bg absolute inset-0" />
        <div className="auth-parking-texture absolute inset-0" />

        <div className="relative grid w-full max-w-5xl items-center gap-8 lg:grid-cols-[1fr_420px]">
          <div className="text-center lg:text-left">
            <div className="inline-flex items-end leading-none tracking-tight drop-shadow-[0_2px_10px_rgba(0,0,0,0.45)]">
              <span className="text-5xl font-black sm:text-6xl">Lot</span>
              <span className="text-5xl font-light sm:text-6xl">Mapper</span>
            </div>
            <p className="mt-4 text-base font-medium text-auth-tagline sm:text-lg">
              Geospatial parking lot detection pipeline
            </p>
            <div className="mx-auto mt-8 h-px w-40 bg-brand-accent lg:mx-0" />
          </div>

          <section className="rounded-lg border border-black/10 bg-auth-panel/95 p-7 text-auth-heading shadow-2xl shadow-black/20 backdrop-blur dark:border-white/10 dark:shadow-black/35 sm:p-8">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-auth-heading">{title}</h1>
              {subtitle && <p className="mt-2 text-sm leading-6 text-auth-body">{subtitle}</p>}
            </div>
            <div className="mt-6">{children}</div>
          </section>
        </div>
      </div>
    </div>
  )
}

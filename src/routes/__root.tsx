import type { ReactNode } from 'react'
import { createRootRoute, HeadContent, Outlet, Scripts } from '@tanstack/react-router'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { name: 'theme-color', content: '#000000' },
      {
        name: 'description',
        content:
          'CLIO — Continuity & Lineage Intelligence Operator — is a script continuity and lineage workspace.',
      },
      { title: 'CLIO — Continuity & Lineage Intelligence Operator' },
    ],
    links: [
      { rel: 'icon', href: '/clio-cut-monogram.png', type: 'image/png' },
      { rel: 'stylesheet', href: '/clio.css' },
    ],
  }),
  notFoundComponent: RootNotFound,
  component: RootDocument,
})

function RootNotFound() {
  return <main style={{ padding: '2rem', color: '#d9d9d9', background: '#000' }}>CLIO / ROUTE NOT FOUND</main>
}

function RootDocument() {
  return (
    <DocumentShell>
      <Outlet />
    </DocumentShell>
  )
}

function DocumentShell({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>{children}<Scripts /></body>
    </html>
  )
}

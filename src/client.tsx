import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { getRouter } from './router'
import './styles.css'

// The Firebase Hosting build is a static client. Rendering the router directly
// keeps it deployable without a serialized TanStack SSR document; the same
// route tree is used by the local Start server.
createRoot(document).render(
  <StrictMode>
    <RouterProvider router={getRouter()} />
  </StrictMode>,
)

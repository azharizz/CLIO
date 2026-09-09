import { createFileRoute } from '@tanstack/react-router'
import { backendFetch } from '../lib/api'
import { createFallbackSnapshot, setWorkspaceSnapshot } from '../lib/workspace'

/** Local capture/test reset; it is intentionally not used by the product UI. */
export const Route = createFileRoute('/api/test/reset')({
  server: {
    handlers: {
      POST: async () => {
        let backend = 'unavailable'
        try {
          await backendFetch('/test/reset', { method: 'POST' })
          backend = 'reset'
        } catch {
          // The local mirror is still reset below.
        }
        return Response.json({ ...setWorkspaceSnapshot(createFallbackSnapshot()), reset: backend }, { status: 200 })
      },
    },
  },
})

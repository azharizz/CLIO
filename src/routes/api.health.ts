import { createFileRoute } from '@tanstack/react-router'
import { backendFetch } from '../lib/api'

export const Route = createFileRoute('/api/health')({
  server: {
    handlers: {
      GET: async () => {
        try {
          const backend = await backendFetch<{ status?: string; runtime_mode?: string; storage_mode?: string }>('/health')
          return Response.json({ status: backend.status ?? 'ok', app: 'clio', name: 'CLIO', displayName: 'Continuity & Lineage Intelligence Operator', runtime: backend.runtime_mode ?? 'simulation', storage: backend.storage_mode, source: 'fastapi' }, { headers: { 'X-CLIO-Source': 'fastapi' } })
        } catch {
          return Response.json({ status: 'ok', app: 'clio', name: 'CLIO', displayName: 'Continuity & Lineage Intelligence Operator', runtime: 'simulation', source: 'local-fallback' }, { headers: { 'X-CLIO-Source': 'local-fallback' } })
        }
      },
    },
  },
})

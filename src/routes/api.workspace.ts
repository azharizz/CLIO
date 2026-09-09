import { createFileRoute } from '@tanstack/react-router'
import { BackendUnavailableError, fetchWorkspaceSnapshot } from '../lib/api'
import { readWorkspaceSnapshot } from '../lib/workspace'

export const Route = createFileRoute('/api/workspace')({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const url = new URL(request.url)
        const filmId = url.searchParams.get('filmId') ?? 'demo-feature'
        const revisionId = url.searchParams.get('revisionId') ?? 'rev-05'
        try {
          return Response.json(await fetchWorkspaceSnapshot(filmId, revisionId))
        } catch (error) {
          const fallback = readWorkspaceSnapshot()
          const diagnostics = {
            attemptedSource: error instanceof BackendUnavailableError ? error.attemptedSource : 'python_fastapi',
            fallbackSource: 'computed',
            message: error instanceof Error ? error.message : 'FastAPI unavailable',
          }
          // Keep the normalized snapshot usable while making the attempted
          // provider and fallback explicit to API consumers and documentation.
          return Response.json(
            { ...fallback, providerError: diagnostics, provider_error: diagnostics },
            {
              headers: {
                'X-CLIO-Source': 'local-fallback',
                'X-CLIO-Provider-Error': JSON.stringify(diagnostics),
              },
            },
          )
        }
      },
    },
  },
})

import { createFileRoute } from '@tanstack/react-router'
import { BackendUnavailableError, fetchWorkspaceSnapshot } from '../lib/api'
import { readWorkspaceSnapshot } from '../lib/workspace'
import { formatWorkspaceCacheAge, readWorkspaceCache, writeWorkspaceCache } from '../lib/workspace-cache'

const inFlight = new Map<string, Promise<Awaited<ReturnType<typeof fetchWorkspaceSnapshot>>>>()

function cacheHeaders(cacheState: 'HIT' | 'MISS' | 'STALE') {
  return {
    // The browser cache is a secondary optimization; the app's session cache
    // owns stale-while-revalidate behavior and can be invalidated after writes.
    'Cache-Control': 'private, max-age=15, stale-while-revalidate=60',
    'X-CLIO-Cache': cacheState,
  }
}

export const Route = createFileRoute('/api/workspace')({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const url = new URL(request.url)
        const filmId = url.searchParams.get('filmId') ?? 'demo-feature'
        const revisionId = url.searchParams.get('revisionId') ?? 'rev-05'
        const key = `${filmId}::${revisionId}`
        const bypassCache = request.headers.get('cache-control')?.toLowerCase().includes('no-cache')
          || request.headers.get('x-clio-refresh') === '1'
        const cached = readWorkspaceCache(filmId, revisionId)
        if (!bypassCache && cached?.isFresh) {
          return Response.json(cached.snapshot, {
            headers: {
              ...cacheHeaders('HIT'),
              'X-CLIO-Cache-Age': formatWorkspaceCacheAge(cached.ageMs),
            },
          })
        }

        let pending = inFlight.get(key)
        if (!pending) {
          pending = fetchWorkspaceSnapshot(filmId, revisionId)
          inFlight.set(key, pending)
        }
        try {
          const snapshot = await pending
          writeWorkspaceCache(snapshot)
          return Response.json(snapshot, { headers: cacheHeaders('MISS') })
        } catch (error) {
          const stale = cached ?? readWorkspaceCache(filmId, revisionId)
          const fallback = readWorkspaceSnapshot()
          const diagnostics = {
            attemptedSource: error instanceof BackendUnavailableError ? error.attemptedSource : 'python_fastapi',
            fallbackSource: 'computed',
            message: error instanceof Error ? error.message : 'FastAPI unavailable',
          }
          if (stale) {
            return Response.json(
              { ...stale.snapshot, providerError: diagnostics, provider_error: diagnostics },
              {
                headers: {
                  ...cacheHeaders('STALE'),
                  'X-CLIO-Cache-Age': formatWorkspaceCacheAge(stale.ageMs),
                  'X-CLIO-Provider-Error': JSON.stringify(diagnostics),
                },
              },
            )
          }
          // Keep the normalized snapshot usable while making the attempted
          // provider and fallback explicit to API consumers and documentation.
          return Response.json(
            { ...fallback, providerError: diagnostics, provider_error: diagnostics },
            {
              headers: {
                ...cacheHeaders('MISS'),
                'X-CLIO-Source': 'local-fallback',
                'X-CLIO-Provider-Error': JSON.stringify(diagnostics),
              },
            },
          )
        } finally {
          if (inFlight.get(key) === pending) inFlight.delete(key)
        }
      },
    },
  },
})

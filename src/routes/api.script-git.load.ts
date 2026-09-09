import { createFileRoute } from '@tanstack/react-router'
import { BackendUnavailableError, backendFetch } from '../lib/api'

export const Route = createFileRoute('/api/script-git/load')({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const body = await request.json().catch(() => ({}))
        try {
          const payload = await backendFetch<Record<string, unknown>>('/script-git/load', {
            method: 'POST',
            body: JSON.stringify(body),
          }, 12_000)
          return Response.json(payload, { headers: { 'X-CLIO-Source': 'github' } })
        } catch (error) {
          if (error instanceof BackendUnavailableError) {
            return Response.json(
              error.responseBody ?? { detail: { error_code: 'script_git.unavailable', message: error.message } },
              { status: error.status && error.status >= 400 ? error.status : 502, headers: { 'X-CLIO-Source': 'github-error' } },
            )
          }
          throw error
        }
      },
    },
  },
})

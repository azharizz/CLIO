import { createFileRoute } from '@tanstack/react-router'
import { backendBaseUrl } from '../lib/api'
import { createAgentEventStream, readWorkspaceSnapshot } from '../lib/workspace'

const encoder = new TextEncoder()

export const Route = createFileRoute('/api/agent-runs/$runId/events')({
  server: {
    handlers: {
      GET: async ({ params, request }) => {
        // The browser remains same-origin; only this server route knows the
        // optional FastAPI transport.  A short timeout keeps the local demo
        // usable when the Python service is intentionally stopped.
        if (!params.runId.startsWith('sim-')) {
          const controller = new AbortController()
          const timeout = setTimeout(() => controller.abort(), 1800)
          try {
            const response = await fetch(`${backendBaseUrl()}/api/v1/agent-runs/${encodeURIComponent(params.runId)}/stream`, {
              headers: { Accept: 'text/event-stream' },
              signal: controller.signal,
            })
            if (response.ok && response.body) {
              return new Response(response.body, {
                status: response.status,
                headers: {
                  'Content-Type': 'text/event-stream; charset=utf-8',
                  'Cache-Control': 'no-cache, no-transform',
                  Connection: 'keep-alive',
                  'X-CLIO-Source': 'fastapi',
                },
              })
            }
          } catch {
            // Fall through to the local provider when FastAPI is unavailable.
          } finally {
            clearTimeout(timeout)
          }
        }
        const url = new URL(request.url)
        const action = url.searchParams.get('action') as 'inspect' | 'edit' | 'remove' | 'add' | null
        const focusNode = url.searchParams.get('focus') || undefined
        const events = createAgentEventStream(readWorkspaceSnapshot(), {
          ...(action ? { action } : {}),
          ...(focusNode ? { focusNode } : {}),
        })
        const body = new ReadableStream<Uint8Array>({
          async start(controller) {
            controller.enqueue(encoder.encode(`event: agent.started\ndata: ${JSON.stringify({ runId: params.runId, provenance: { source: 'agent_simulation', label: 'LOCAL SIMULATION' } })}\n\n`))
            for (const event of events) {
              controller.enqueue(encoder.encode(`event: agent.${event.phase}\ndata: ${JSON.stringify(event)}\n\n`))
              await new Promise((resolve) => setTimeout(resolve, 300))
            }
            controller.enqueue(encoder.encode('event: agent.done\ndata: {"status":"complete"}\n\n'))
            controller.close()
          },
        })
        return new Response(body, { headers: { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-cache, no-transform', Connection: 'keep-alive', 'X-CLIO-Source': 'local-simulation' } })
      },
    },
  },
})

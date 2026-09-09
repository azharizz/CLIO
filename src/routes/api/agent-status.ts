import { createFileRoute } from '@tanstack/react-router'
import { createAgentEventStream, readWorkspaceSnapshot } from '../../lib/workspace'

const encoder = new TextEncoder()

function eventStream() {
  const events = createAgentEventStream(readWorkspaceSnapshot())
  let timer: ReturnType<typeof setTimeout> | undefined
  return new ReadableStream<Uint8Array>({
    start(controller) {
      let index = 0
      const push = () => {
        const event = events[index]
        if (!event) {
          controller.enqueue(encoder.encode('event: done\ndata: {"status":"complete"}\n\n'))
          controller.close()
          return
        }
        controller.enqueue(encoder.encode(`event: status\ndata: ${JSON.stringify(event)}\n\n`))
        index += 1
        timer = setTimeout(push, 520)
      }
      timer = setTimeout(push, 160)
    },
    cancel() {
      if (timer) clearTimeout(timer)
    },
  })
}

export const Route = createFileRoute('/api/agent-status')({
  server: {
    handlers: {
      GET: () => new Response(eventStream(), {
        headers: {
          'Content-Type': 'text/event-stream; charset=utf-8',
          'Cache-Control': 'no-cache, no-transform',
          Connection: 'keep-alive',
        },
      }),
    },
  },
})

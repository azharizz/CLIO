import { createFileRoute } from '@tanstack/react-router'
import { backendFetch } from '../lib/api'
import { readWorkspaceSnapshot } from '../lib/workspace'

export const Route = createFileRoute('/api/provenance/$deliveryId')({
  server: {
    handlers: {
      GET: async ({ params }) => {
        try {
          const response = await backendFetch(`/provenance/${encodeURIComponent(params.deliveryId)}`)
          return Response.json(response, { headers: { 'X-CLIO-Source': 'fastapi' } })
        } catch {
          // Keep the compatibility endpoint inspectable without introducing a
          // second script graph or synthetic release package.
        }
        const snapshot = readWorkspaceSnapshot()
        const variant = snapshot.deliveryVariants.find((item) => item.id === params.deliveryId)
        return Response.json({
          deliveryId: params.deliveryId,
          path: ['revision-v5', 'scene-47', params.deliveryId],
          variant: variant ?? null,
          approvals: snapshot.approvals,
          provenance: variant?.provenance ?? snapshot.dataSource,
        })
      },
    },
  },
})

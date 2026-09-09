import { createFileRoute } from '@tanstack/react-router'
import { ClioWorkspace } from './index'
import { createFallbackSnapshot } from '../lib/workspace'

export const Route = createFileRoute('/workspace')({
  // Keep the alternate entry point just as responsive as `/`; the workspace
  // component hydrates its authoritative snapshot in the background.
  loader: () => createFallbackSnapshot(),
  component: WorkspaceRoute,
  head: () => ({
    meta: [{ title: 'CLIO — Continuity & Lineage Intelligence Operator' }],
  }),
})

function WorkspaceRoute() {
  const loaderData = Route.useLoaderData()
  return <ClioWorkspace loaderData={loaderData} />
}

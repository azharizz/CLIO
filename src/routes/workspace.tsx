import { createFileRoute } from '@tanstack/react-router'
import { ClioWorkspace } from './index'
import { loadWorkspaceSnapshot } from '../lib/server-functions'

export const Route = createFileRoute('/workspace')({
  loader: () => loadWorkspaceSnapshot(),
  component: WorkspaceRoute,
  head: () => ({
    meta: [{ title: 'CLIO — Continuity & Lineage Intelligence Operator' }],
  }),
})

function WorkspaceRoute() {
  const loaderData = Route.useLoaderData()
  return <ClioWorkspace loaderData={loaderData} />
}

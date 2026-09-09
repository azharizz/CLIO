import type { EdgeProps } from '@xyflow/react'
import { BaseEdge, getSmoothStepPath } from '@xyflow/react'
import type { GraphEdgeData } from '../lib/contracts'

export function OrthogonalEdge({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, data }: EdgeProps) {
  const edge = data as unknown as GraphEdgeData & { muted?: boolean; active?: boolean }
  const [path] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 0, offset: 18 })
  return (
    <BaseEdge
      path={path}
      className={[
        'fg-edge',
        `fg-edge--${edge?.tone ?? 'understood'}`,
        `fg-edge-kind--${edge?.kind ?? 'backbone'}`,
        edge?.muted ? 'is-muted' : '',
        edge?.active ? 'is-active' : '',
      ].filter(Boolean).join(' ')}
      interactionWidth={12}
    />
  )
}

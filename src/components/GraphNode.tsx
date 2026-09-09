import type { NodeProps } from '@xyflow/react'
import { Handle, Position } from '@xyflow/react'
import type { GraphNodeData } from '../lib/contracts'
import { formatClock } from '../lib/workspace'

function roleFor(frame: GraphNodeData): string {
  if (frame.kind === 'revision') return 'SOURCE'
  if (frame.kind === 'scene') return 'SCENE'
  if (frame.kind === 'beat') return 'BEAT'
  return 'SCRIPT'
}

function timingFor(frame: GraphNodeData): string | undefined {
  if (typeof frame.startSeconds !== 'number' || typeof frame.endSeconds !== 'number') return undefined
  return `${formatClock(frame.startSeconds)} → ${formatClock(frame.endSeconds)}`
}

/** A script node is a 2.39:1 frame with text and its exact cut duration. */
export function GraphNode({ id, data, selected = false }: NodeProps) {
  const frame = data as unknown as GraphNodeData & {
    muted?: boolean
    pathActive?: boolean
    childrenExpanded?: boolean
    onToggleChildren?: () => void
  }
  const role = roleFor(frame)
  const timing = timingFor(frame)
  const duration = typeof frame.durationSeconds === 'number' ? formatClock(frame.durationSeconds) : frame.metric
  const sceneMark = frame.sceneNumber
    ? `SC ${frame.sceneNumber}${frame.beatNumber ? ` / B${String(frame.beatNumber).padStart(2, '0')}` : ''}`
    : role
  const className = [
    'fg-frame',
    'fg-script-frame',
    `fg-frame--${frame.status}`,
    `fg-frame--${frame.kind}`,
    selected ? 'is-selected' : '',
    frame.muted ? 'is-muted' : '',
    frame.pathActive ? 'is-path-active' : '',
    frame.split ? 'is-split' : '',
  ].filter(Boolean).join(' ')

  return (
    <article
      className={className}
      aria-label={`${role}: ${sceneMark} ${frame.title}${timing ? `, ${timing}` : ''}${frame.narrationText ? `, narration ${frame.narrationText}` : ''}`}
      title={`${role} · ${frame.scope ?? 'focus'}`}
      data-node-kind={frame.kind}
      data-node-id={id}
      data-node-scope={frame.scope ?? 'focus'}
      data-node-entity={frame.entityType ?? frame.kind}
      data-parent-scene={frame.parentSceneId ?? ''}
    >
      <Handle type="target" position={Position.Left} className="fg-handle" />
      <Handle type="source" position={Position.Right} className="fg-handle" />
      <span className="fg-crop fg-crop--tl" aria-hidden="true" />
      <span className="fg-crop fg-crop--tr" aria-hidden="true" />
      <span className="fg-crop fg-crop--bl" aria-hidden="true" />
      <span className="fg-crop fg-crop--br" aria-hidden="true" />

      <header className="fg-frame__head">
        <span className="fg-eyebrow">{sceneMark}</span>
        <span className="fg-code">{timing ?? frame.code}</span>
        {frame.kind === 'scene' && frame.childCount ? (
          <button
            type="button"
            className="fg-frame__expand"
            aria-label={`${frame.childrenExpanded ? 'Hide' : 'Show'} ${frame.childCount} child beats`}
            aria-pressed={frame.childrenExpanded}
            onClick={(event) => { event.stopPropagation(); frame.onToggleChildren?.() }}
          >
            {frame.childrenExpanded ? `−${frame.childCount}` : `+${frame.childCount}`}
          </button>
        ) : null}
      </header>

      <div className="fg-frame__body">
        <h3>{frame.title}</h3>
        {frame.scriptText || frame.detail ? <p>{frame.scriptText ?? frame.detail}</p> : null}
        {frame.narrationText ? <span className="fg-narration-preview">↳ {frame.narrationText}</span> : null}
      </div>

      <footer className="fg-frame__foot">
        <span className={`fg-state fg-state--${frame.status}`}>
          <span className="fg-state__mark" aria-hidden="true" />
          <span>{frame.status === 'understood' ? 'TRACED' : frame.status.toUpperCase()}</span>
        </span>
        <span className="fg-metric">{duration}</span>
        <span className="fg-secondary">{frame.secondary ?? 'SCRIPT'}</span>
      </footer>
    </article>
  )
}

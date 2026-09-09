import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { GraphNode } from '../components/GraphNode'
import { OrthogonalEdge } from '../components/OrthogonalEdge'
import { addEvent, type StreamEvent } from '../components/AgentStream'
import { NodeEditorOverlay } from '../components/NodeEditorOverlay'
import { OnboardingOverlay } from '../components/OnboardingOverlay'
import { ScriptGitOverlay } from '../components/ScriptGitOverlay'
import { loadWorkspaceSnapshot } from '../lib/server-functions'
import type {
  AgentEvent,
  GraphNodeDraft,
  GraphNodeData,
  GraphViewMode,
  Provenance,
  WorkflowPhase,
  WorkspaceNode,
  WorkspaceSnapshot,
} from '../lib/contracts'
import { buildFilmMap } from '../lib/film-map'
import {
  createAgentEventStream,
  createLocalGraphNode,
  deleteLocalGraphNode,
  downstreamFor,
  formatClock,
  lineageFor,
  updateLocalGraphNode,
} from '../lib/workspace'

const nodeTypes = { filmFrame: GraphNode }
const edgeTypes = { orthogonal: OrthogonalEdge }
type FlowNode = Node<Record<string, unknown>>
type FlowEdge = Edge<Record<string, unknown>>
type AgentAction = 'inspect' | 'edit' | 'remove' | 'add'
const ONBOARDING_STORAGE_KEY = 'clio-onboarding-complete'

const AGENT_ACTIONS: Array<{ id: AgentAction; label: string; short: string }> = [
  { id: 'inspect', label: 'EXPLAIN', short: 'PATH' },
  { id: 'edit', label: 'EDIT', short: 'AFFECTED' },
  { id: 'remove', label: 'REMOVE', short: 'TIME' },
  { id: 'add', label: 'ADD', short: 'LINK' },
]

export const Route = createFileRoute('/')({
  loader: () => loadWorkspaceSnapshot(),
  component: RootWorkspace,
  head: () => ({ meta: [{ title: 'CLIO — Continuity & Lineage Intelligence Operator' }] }),
})

function RootWorkspace() {
  const loaderData = Route.useLoaderData()
  return <ClioWorkspace loaderData={loaderData} />
}

function phaseFor(node: WorkspaceNode | undefined): WorkflowPhase {
  if (!node) return 'workspace'
  if (node.data.kind === 'revision') return 'revision'
  if (node.data.kind === 'scene' || node.data.kind === 'beat') return 'scene'
  return 'workspace'
}

function nodeRole(node: WorkspaceNode | undefined): string {
  if (node?.data.kind === 'revision') return 'SOURCE'
  if (node?.data.kind === 'scene') return 'SCENE'
  if (node?.data.kind === 'beat') return 'BEAT'
  return 'SCRIPT'
}

function nodeName(node: WorkspaceNode | undefined): string {
  if (!node) return 'NONE'
  if (node.data.sceneNumber && node.data.beatNumber) return `SC ${node.data.sceneNumber} / B${String(node.data.beatNumber).padStart(2, '0')}`
  return node.data.sceneNumber ? `SC ${node.data.sceneNumber}` : node.data.title
}

function nodeTime(node: WorkspaceNode | undefined): string {
  if (typeof node?.data.startSeconds !== 'number' || typeof node.data.endSeconds !== 'number') return '—'
  return `${formatClock(node.data.startSeconds)} → ${formatClock(node.data.endSeconds)}`
}

function ProvenanceTag({ value }: { value: Provenance | undefined }) {
  return (
    <span className={`fg-provenance fg-provenance--${value?.source ?? 'computed'}`}>
      <span className="fg-provenance__mark" aria-hidden="true" />
      {value?.label ?? 'COMPUTED'}
    </span>
  )
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>
}

function agentPromptFor(action: AgentAction, node: WorkspaceNode | undefined): string {
  const focus = nodeName(node)
  if (action === 'edit') return `Edit ${focus}: which scenes are affected?`
  if (action === 'remove') return `Remove ${focus}: how much time changes and what is no longer needed?`
  if (action === 'add') return `Add beside ${focus}: where can it connect?`
  return `Explain ${focus}: what comes before and after it?`
}

function AgentOverlay({
  node,
  action,
  prompt,
  events,
  running,
  onAction,
  onPrompt,
  onRun,
  onClose,
}: {
  node: WorkspaceNode | undefined
  action: AgentAction
  prompt: string
  events: StreamEvent[]
  running: boolean
  onAction: (action: AgentAction) => void
  onPrompt: (prompt: string) => void
  onRun: () => void
  onClose: () => void
}) {
  const graphEvent = events.find((event) => event.stage === 'graph')
  const timeEvent = events.find((event) => event.stage === 'analytics')
  const criticEvent = events.find((event) => event.stage === 'critic')
  const outputEvents = [graphEvent, timeEvent, criticEvent].filter((event): event is StreamEvent => Boolean(event))

  return (
    <section className="fg-agent-overlay" role="dialog" aria-modal="false" aria-label="CLIO agent">
      <header className="fg-agent-overlay__head">
        <div>
          <span className="fg-label">AGENTIC RUN</span>
          <span className="fg-micro">LOCAL SIMULATION · NO AUTO-WRITES</span>
        </div>
        <button type="button" className="fg-overlay-close" onClick={onClose} aria-label="Close agent">×</button>
      </header>
      <div className="fg-agent-overlay__target">
        <span className="fg-label">FOCUS</span>
        <strong>{nodeName(node)}</strong>
        <span>{nodeRole(node)} · {nodeTime(node)}</span>
      </div>
      <div className="fg-agent-actions" role="group" aria-label="Agent operation">
        {AGENT_ACTIONS.map((item) => (
          <button
            type="button"
            key={item.id}
            className={action === item.id ? 'is-active' : ''}
            onClick={() => onAction(item.id)}
            aria-pressed={action === item.id}
          >
            <span>{item.label}</span><small>{item.short}</small>
          </button>
        ))}
      </div>
      <div className="fg-agent-prompt">
        <label htmlFor="agent-prompt"><span className="fg-label">ASK</span></label>
        <textarea id="agent-prompt" value={prompt} onChange={(event) => onPrompt(event.target.value)} rows={1} autoFocus />
        <button type="button" className="fg-action" onClick={onRun} disabled={running}>
          {running ? 'THINKING…' : 'ANALYZE'}
        </button>
      </div>
      <div className="fg-agent-output" aria-live="polite">
        {events.length === 0 ? <span className="fg-quiet-note">ASK WHAT CHANGES, WHAT CONNECTS, OR WHAT CAN BE REMOVED.</span> : null}
        {outputEvents.map((event) => (
          <div className={`fg-agent-output__item fg-agent-output__item--${event.tone}`} key={event.id}>
            <strong>{event.label}</strong>
            <span>{event.detail}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function ScriptDiff({ snapshot }: { snapshot: WorkspaceSnapshot }) {
  return (
    <section className="fg-script-diff" aria-label="Revision text">
      <span className="fg-label">SCRIPT CHANGE</span>
      <div><span>BEFORE</span><p>{snapshot.revisionBefore}</p></div>
      <div><span>AFTER</span><p>{snapshot.revisionAfter}</p></div>
    </section>
  )
}

function SceneInspector({
  snapshot,
  node,
  onAgent,
  expandedSceneIds,
  onToggleBeats,
  onSelectNode,
  onEditNode,
  onCreateScene,
  onCreateBeat,
  onDeleteNode,
  crudError,
}: {
  snapshot: WorkspaceSnapshot
  node: WorkspaceNode | undefined
  onAgent: (action: AgentAction) => void
  expandedSceneIds: ReadonlySet<string>
  onToggleBeats: (sceneId: string) => void
  onSelectNode: (node: WorkspaceNode) => void
  onEditNode: (node: WorkspaceNode) => void
  onCreateScene: () => void
  onCreateBeat: (scene: WorkspaceNode) => void
  onDeleteNode: (node: WorkspaceNode) => void
  crudError?: string
}) {
  const upstream = useMemo(() => lineageFor(snapshot, node?.id ?? '').filter((id) => id !== node?.id), [snapshot, node?.id])
  const downstream = useMemo(() => downstreamFor(snapshot, node?.id ?? '').filter((id) => id !== node?.id), [snapshot, node?.id])
  const contextUpstream = useMemo(() => upstream.filter((id) => node?.data.kind === 'beat' || snapshot.graph.nodes.find((item) => item.id === id)?.data.kind !== 'beat'), [snapshot, node?.data.kind, upstream])
  const contextDownstream = useMemo(() => downstream.filter((id) => node?.data.kind === 'beat' || snapshot.graph.nodes.find((item) => item.id === id)?.data.kind !== 'beat'), [snapshot, node?.data.kind, downstream])
  const lookup = (ids: string[]) => ids
    .map((id) => snapshot.graph.nodes.find((item) => item.id === id))
    .filter((item): item is WorkspaceNode => item !== undefined && item.data.kind !== 'beat')
    .map((item) => nodeName(item))
    .filter((value, index, values) => values.indexOf(value) === index)
    .join(' · ') || 'NONE'
  const duration = typeof node?.data.durationSeconds === 'number' ? formatClock(node.data.durationSeconds) : '—'
  const childBeats = useMemo(() => snapshot.graph.nodes
    .filter((item) => item.data.kind === 'beat' && item.data.parentSceneId === node?.id)
    .sort((a, b) => (a.data.beatNumber ?? 0) - (b.data.beatNumber ?? 0)), [snapshot, node?.id])
  const parentScene = node?.data.parentSceneId
    ? snapshot.graph.nodes.find((item) => item.id === node.data.parentSceneId)
    : undefined

  return (
    <>
      <section className="fg-node-identity" aria-label="Selected node identity">
        <KeyValue label="TYPE" value={nodeRole(node)} />
        <KeyValue label="START → END" value={nodeTime(node)} />
        <KeyValue label="DURATION" value={duration} />
      </section>
      {node?.data.kind === 'revision' ? <ScriptDiff snapshot={snapshot} /> : null}
      {node?.data.kind === 'scene' || node?.data.kind === 'beat' ? (
        <section className="fg-script-text" aria-label="Script text">
          <span className="fg-label">SCRIPT TEXT</span>
          <p>{node.data.scriptText ?? node.data.detail}</p>
          <span className="fg-label fg-label--narration">NARRATION</span>
          <p className="fg-narration-text">{node.data.narrationText ?? '—'}</p>
        </section>
      ) : null}
      {node?.data.kind === 'beat' && parentScene ? (
        <section className="fg-beat-parent" aria-label="Parent scene">
          <span className="fg-label">PARENT SCENE</span>
          <button type="button" onClick={() => onSelectNode(parentScene)}>{nodeName(parentScene)} · {parentScene.data.title}</button>
        </section>
      ) : null}
      {node?.data.kind === 'scene' && childBeats.length > 0 ? (
        <section className="fg-beats-block" aria-label={`Child beats for scene ${node.data.sceneNumber}`}>
          <div className="fg-section-line">
            <span className="fg-label">CHILD BEATS / {childBeats.length}</span>
            <button type="button" className="fg-beat-toggle" onClick={() => onToggleBeats(node.id)} aria-pressed={expandedSceneIds.has(node.id)}>
              {expandedSceneIds.has(node.id) ? 'HIDE MAP' : 'SHOW MAP'}
            </button>
          </div>
          <div className="fg-beat-list">
            {childBeats.map((beat) => (
              <button type="button" className={`fg-beat-row ${beat.id === node?.id ? 'is-selected' : ''}`} key={beat.id} onClick={() => onSelectNode(beat)}>
                <span className="fg-beat-row__index">B{String(beat.data.beatNumber ?? 0).padStart(2, '0')}</span>
                <span className="fg-beat-row__copy"><strong>{beat.data.title}</strong><small>{beat.data.scriptText}</small><em>{beat.data.narrationText}</em></span>
                <span className="fg-beat-row__time">{nodeTime(beat)}<br />{formatClock(beat.data.durationSeconds ?? 0)}</span>
              </button>
            ))}
          </div>
        </section>
      ) : null}
      <section className="fg-context-block" aria-label="Graph impact">
        <div className="fg-section-line"><span className="fg-label">GRAPH CONTEXT</span><span className="fg-micro">{contextUpstream.length + contextDownstream.length} LINKS</span></div>
        <div className="fg-kv-list">
          <KeyValue label={`UPSTREAM / ${contextUpstream.length}`} value={lookup(contextUpstream)} />
          <KeyValue label={`DOWNSTREAM / ${contextDownstream.length}`} value={lookup(contextDownstream)} />
        </div>
      </section>
      <section className="fg-agent-card">
        <div className="fg-section-line"><span className="fg-label">AGENTIC RUN</span><span className="fg-micro">PROPOSALS ONLY</span></div>
        <div className="fg-agent-shortcuts" role="group" aria-label="Agent node actions">
          <button type="button" onClick={() => onAgent('edit')}>EDIT</button>
          <button type="button" onClick={() => onAgent('remove')}>REMOVE</button>
          <button type="button" onClick={() => onAgent('add')}>ADD</button>
        </div>
        <button type="button" className="fg-action fg-action--wide" onClick={() => onAgent('inspect')} aria-label="ASK AGENT">
          ASK AGENT
        </button>
      </section>
      <section className="fg-node-actions" aria-label="Node actions">
        <div className="fg-section-line"><span className="fg-label">NODE CONTROL</span><span className="fg-micro">HUMAN WRITE</span></div>
        {node?.data.kind === 'scene' || node?.data.kind === 'beat' ? (
          <div className="fg-node-actions__row">
            <button type="button" onClick={() => onEditNode(node)}>EDIT</button>
            {node.data.kind === 'scene' ? <button type="button" onClick={() => onCreateBeat(node)}>ADD BEAT</button> : null}
            <button type="button" className="is-danger" onClick={() => onDeleteNode(node)}>DELETE</button>
          </div>
        ) : (
          <button type="button" className="fg-action fg-action--wide" onClick={onCreateScene}>ADD SCENE</button>
        )}
        {crudError ? <p className="fg-inline-error" role="alert">{crudError}</p> : null}
      </section>
    </>
  )
}

export function ClioWorkspace({ loaderData }: { loaderData: WorkspaceSnapshot }) {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot>(loaderData)
  const [selectedNodeId, setSelectedNodeId] = useState(loaderData.selectedNodeId)
  const [phase, setPhase] = useState<WorkflowPhase>(phaseFor(loaderData.graph.nodes.find((node) => node.id === loaderData.selectedNodeId)))
  const [viewMode, setViewMode] = useState<GraphViewMode>('overview')
  const [traceActive, setTraceActive] = useState(true)
  const [feed, setFeed] = useState<StreamEvent[]>([])
  const [agentRunning, setAgentRunning] = useState(false)
  const [hydrated, setHydrated] = useState(false)
  const [indexOpen, setIndexOpen] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [agentOpen, setAgentOpen] = useState(false)
  const [gitOpen, setGitOpen] = useState(false)
  const [agentAction, setAgentAction] = useState<AgentAction>('inspect')
  const [agentPrompt, setAgentPrompt] = useState('')
  /** Visibility is local to each parent; hidden beats remain in the snapshot for agent calculations. */
  const [expandedSceneIds, setExpandedSceneIds] = useState<Set<string>>(() => new Set())
  const [onboardingOpen, setOnboardingOpen] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create')
  const [editorNodeId, setEditorNodeId] = useState<string | undefined>(undefined)
  const [editorDefaultKind, setEditorDefaultKind] = useState<'scene' | 'beat'>('scene')
  const [editorDefaultParentId, setEditorDefaultParentId] = useState<string | undefined>(undefined)
  const [crudSaving, setCrudSaving] = useState(false)
  const [crudError, setCrudError] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceNode | undefined>(undefined)
  const flowRef = useRef<ReactFlowInstance | null>(null)
  const streamRef = useRef<EventSource | null>(null)
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setSnapshot(loaderData)
    setSelectedNodeId(loaderData.selectedNodeId)
    setPhase(phaseFor(loaderData.graph.nodes.find((node) => node.id === loaderData.selectedNodeId)))
    setExpandedSceneIds(new Set())
  }, [loaderData])

  useEffect(() => {
    setHydrated(true)
    try {
      setOnboardingOpen(window.localStorage.getItem(ONBOARDING_STORAGE_KEY) !== '1')
    } catch {
      setOnboardingOpen(true)
    }
    return () => {
      streamRef.current?.close()
      if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current)
    }
  }, [])

  const activeGraph = useMemo(() => buildFilmMap(snapshot, expandedSceneIds), [snapshot, expandedSceneIds])
  const selectedNode = activeGraph.nodes.find((node) => node.id === selectedNodeId)
    ?? activeGraph.nodes.find((node) => node.id === snapshot.selectedNodeId)
    ?? activeGraph.nodes.find((node) => node.data.kind === 'scene')
  const lineage = useMemo(
    () => new Set([...lineageFor(snapshot, selectedNode?.id ?? ''), ...downstreamFor(snapshot, selectedNode?.id ?? '')]),
    [snapshot, selectedNode?.id],
  )

  const finishOnboarding = useCallback(() => {
    try { window.localStorage.setItem(ONBOARDING_STORAGE_KEY, '1') } catch { /* private browsing */ }
    setOnboardingOpen(false)
  }, [])

  const freshWorkspace = useCallback(async (): Promise<WorkspaceSnapshot> => {
    const response = await fetch('/api/workspace?filmId=demo-feature&revisionId=rev-05', { headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error(`Workspace refresh failed (${response.status})`)
    return (await response.json()) as WorkspaceSnapshot
  }, [])

  const selectNode = useCallback((node: WorkspaceNode) => {
    finishOnboarding()
    setSelectedNodeId(node.id)
    setPhase(phaseFor(node))
    setTraceActive(true)
    setInspectorOpen(true)
    setIndexOpen(false)
    setAgentOpen(false)
    setGitOpen(false)
    if (node.data.kind === 'beat' && node.data.parentSceneId) {
      setExpandedSceneIds((current) => {
        if (current.has(node.data.parentSceneId!)) return current
        const next = new Set(current)
        next.add(node.data.parentSceneId!)
        return next
      })
    }
  }, [finishOnboarding])

  const toggleBeats = useCallback((sceneId: string) => {
    setExpandedSceneIds((current) => {
      const next = new Set(current)
      if (next.has(sceneId)) next.delete(sceneId)
      else next.add(sceneId)
      return next
    })
  }, [])

  const openAgent = useCallback((action: AgentAction = 'inspect') => {
    finishOnboarding()
    setAgentAction(action)
    setAgentPrompt(agentPromptFor(action, selectedNode))
    setFeed([])
    setAgentOpen(true)
    setIndexOpen(false)
    setInspectorOpen(false)
    setGitOpen(false)
    setPhase('agent')
  }, [finishOnboarding, selectedNode])

  const openScriptGit = useCallback(() => {
    finishOnboarding()
    setGitOpen(true)
    setIndexOpen(false)
    setInspectorOpen(false)
    setAgentOpen(false)
    setPhase('revision')
  }, [finishOnboarding])

  const appliedScriptGit = useCallback(async () => {
    try {
      const refreshed = await freshWorkspace()
      setSnapshot(refreshed)
      setSelectedNodeId(refreshed.selectedNodeId)
      setViewMode('overview')
      setTraceActive(true)
      setGitOpen(false)
      setInspectorOpen(true)
      setPhase('revision')
    } catch {
      // The same-origin apply route updates its local mirror when FastAPI is
      // unavailable; leave the overlay closed and let the next refresh load it.
      setGitOpen(false)
      setInspectorOpen(true)
    }
  }, [freshWorkspace])

  const openCreateNode = useCallback((kind: 'scene' | 'beat' = 'scene', parent?: WorkspaceNode) => {
    finishOnboarding()
    setCrudError('')
    setEditorMode('create')
    setEditorNodeId(undefined)
    setEditorDefaultKind(kind)
    setEditorDefaultParentId(parent?.id)
    if (parent) setSelectedNodeId(parent.id)
    setEditorOpen(true)
    setAgentOpen(false)
    setGitOpen(false)
    setInspectorOpen(false)
    setIndexOpen(false)
  }, [finishOnboarding])

  const openEditNode = useCallback((node: WorkspaceNode) => {
    setCrudError('')
    setEditorMode('edit')
    setEditorNodeId(node.id)
    setEditorDefaultKind(node.data.kind === 'beat' ? 'beat' : 'scene')
    setEditorDefaultParentId(node.data.parentSceneId)
    setEditorOpen(true)
    setAgentOpen(false)
  }, [])

  const saveNode = useCallback(async (draft: GraphNodeDraft) => {
    setCrudSaving(true)
    setCrudError('')
    const targetId = editorNodeId
    let responseReceived = false
    let mutationSucceeded = false
    try {
      const path = editorMode === 'create' ? '/api/graph/nodes' : `/api/graph/nodes/${encodeURIComponent(editorNodeId ?? '')}`
      const response = await fetch(path, {
        method: editorMode === 'create' ? 'POST' : 'PATCH',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          kind: draft.kind,
          sceneNumber: draft.sceneNumber,
          beatNumber: draft.beatNumber,
          parentSceneId: draft.parentSceneId,
          heading: draft.heading,
          scriptText: draft.scriptText,
          narrationText: draft.narrationText,
          startSeconds: draft.startSeconds,
          endSeconds: draft.endSeconds,
          actor: 'EDITORIAL',
          runtime_mode: 'simulation',
        }),
      })
      responseReceived = true
      const payload = await response.json().catch(() => ({})) as Record<string, unknown>
      if (!response.ok) {
        const detail = payload.detail && typeof payload.detail === 'object' ? payload.detail as Record<string, unknown> : {}
        throw new Error(String(detail.message ?? payload.message ?? `Node request failed (${response.status})`))
      }
      mutationSucceeded = true
      // The same-origin route can complete against the in-process mirror when
      // FastAPI is offline. Re-apply that mutation to this browser state
      // instead of immediately asking the unavailable backend for a refresh.
      if (payload.local === true) {
        const local = editorMode === 'create'
          ? createLocalGraphNode(snapshot, draft)
          : updateLocalGraphNode(snapshot, targetId ?? '', draft)
        setSnapshot(local)
        setSelectedNodeId(local.selectedNodeId)
        setEditorOpen(false)
        setInspectorOpen(true)
        setPhase('scene')
        if (draft.kind === 'beat' && draft.parentSceneId) setExpandedSceneIds((current) => new Set(current).add(draft.parentSceneId!))
        return
      }
      const refreshed = await freshWorkspace()
      setSnapshot(refreshed)
      const selectedId = editorMode === 'edit' ? targetId : (typeof payload.id === 'string' ? payload.id : refreshed.selectedNodeId)
      setSelectedNodeId(selectedId ?? refreshed.selectedNodeId)
      setEditorOpen(false)
      setInspectorOpen(true)
      setPhase('scene')
      if (draft.kind === 'beat' && draft.parentSceneId) setExpandedSceneIds((current) => new Set(current).add(draft.parentSceneId!))
    } catch (error) {
      if (mutationSucceeded || responseReceived) {
        setCrudError(error instanceof Error ? error.message : 'Node saved; refresh the workspace to inspect it.')
        return
      }
      // Keep the browser useful when FastAPI is down: the same validation and
      // append-only event mirror powers the local fallback route.
      try {
        const local = editorMode === 'create'
          ? createLocalGraphNode(snapshot, draft)
          : updateLocalGraphNode(snapshot, targetId ?? '', draft)
        setSnapshot(local)
        setSelectedNodeId(local.selectedNodeId)
        setEditorOpen(false)
        setInspectorOpen(true)
        setPhase('scene')
        if (draft.kind === 'beat' && draft.parentSceneId) setExpandedSceneIds((current) => new Set(current).add(draft.parentSceneId!))
      } catch (localError) {
        setCrudError(localError instanceof Error ? localError.message : error instanceof Error ? error.message : 'Unable to save node.')
      }
    } finally {
      setCrudSaving(false)
    }
  }, [editorMode, editorNodeId, freshWorkspace, snapshot])

  const requestDeleteNode = useCallback((node: WorkspaceNode) => {
    setCrudError('')
    setDeleteTarget(node)
    setEditorOpen(false)
  }, [])

  const confirmDeleteNode = useCallback(async () => {
    if (!deleteTarget) return
    const target = deleteTarget
    setCrudSaving(true)
    setCrudError('')
    let responseReceived = false
    try {
      const response = await fetch(`/api/graph/nodes/${encodeURIComponent(target.id)}?actor=EDITORIAL&runtimeMode=simulation`, { method: 'DELETE', headers: { Accept: 'application/json' } })
      responseReceived = true
      const payload = await response.json().catch(() => ({})) as Record<string, unknown>
      if (!response.ok) {
        const detail = payload.detail && typeof payload.detail === 'object' ? payload.detail as Record<string, unknown> : {}
        throw new Error(String(detail.message ?? `Delete failed (${response.status})`))
      }
      if (payload.local === true) {
        const local = deleteLocalGraphNode(snapshot, target.id)
        setSnapshot(local)
        setSelectedNodeId(local.selectedNodeId)
        return
      }
      const refreshed = await freshWorkspace()
      setSnapshot(refreshed)
      setSelectedNodeId(refreshed.selectedNodeId)
    } catch (error) {
      if (responseReceived) {
        setCrudError(error instanceof Error ? error.message : 'Delete failed.')
        setDeleteTarget(undefined)
        setCrudSaving(false)
        return
      }
      try {
        const local = deleteLocalGraphNode(snapshot, target.id)
        setSnapshot(local)
        setSelectedNodeId(local.selectedNodeId)
      } catch (localError) {
        setCrudError(localError instanceof Error ? localError.message : error instanceof Error ? error.message : 'Unable to delete node.')
      }
    } finally {
      setCrudSaving(false)
      setDeleteTarget(undefined)
      setInspectorOpen(false)
    }
  }, [deleteTarget, freshWorkspace, snapshot])

  const chooseAgentAction = (action: AgentAction) => {
    setAgentAction(action)
    setAgentPrompt(agentPromptFor(action, selectedNode))
  }

  const flowNodes: FlowNode[] = activeGraph.nodes.map((node) => ({
    id: node.id,
    position: node.position,
    type: 'filmFrame',
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    selected: node.id === selectedNode?.id,
    data: {
      ...node.data,
      childrenExpanded: node.data.kind === 'scene' && expandedSceneIds.has(node.id),
      onToggleChildren: node.data.kind === 'scene' && node.data.childCount
        ? () => toggleBeats(node.id)
        : undefined,
      muted: viewMode === 'trace' && traceActive && lineage.size > 0 && !lineage.has(node.id),
      pathActive: viewMode === 'trace' && traceActive && lineage.has(node.id),
    } as Record<string, unknown>,
  }))

  const flowEdges: FlowEdge[] = activeGraph.edges.map((edge) => {
    const active = viewMode === 'trace' && traceActive && lineage.has(edge.source) && lineage.has(edge.target)
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'orthogonal',
      animated: active && edge.data.tone === 'understood',
      data: { ...edge.data, active, muted: viewMode === 'trace' && traceActive && !active } as Record<string, unknown>,
    }
  })

  useEffect(() => {
    const timer = window.setTimeout(() => {
      flowRef.current?.fitView({ duration: 0, padding: viewMode === 'overview' ? 0.13 : 0.08 })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [viewMode, activeGraph.nodes.length, activeGraph.edges.length])

  const runLocalFallback = useCallback(() => {
    const events = toStreamEvents(createAgentEventStream(snapshot, {
      action: agentAction,
      prompt: agentPrompt,
      ...(selectedNode?.id ? { focusNode: selectedNode.id } : {}),
    }))
    setFeed((current) => events.reduce((items, event) => addEvent(items, event), current))
  }, [agentAction, agentPrompt, selectedNode?.id, snapshot])

  const runAgent = async () => {
    setPhase('agent')
    setAgentOpen(true)
    setAgentRunning(true)
    setFeed([])
    streamRef.current?.close()
    if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current)
    let runId = ''
    try {
      const response = await fetch('/api/agent-runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflowId: snapshot.workspaceId,
          prompt: `[${agentAction.toUpperCase()} NODE] ${agentPrompt.trim() || agentPromptFor(agentAction, selectedNode)}`,
          stage: 'Script',
          action: agentAction,
          focusNode: selectedNode?.id,
          runtime_mode: 'simulation',
        }),
      })
      if (response.ok) runId = ((await response.json()) as { id?: string }).id ?? ''
    } catch {
      // The client-side stream fallback below remains usable without Python.
    }
    if (!runId) {
      runLocalFallback()
      setAgentRunning(false)
      return
    }
    const streamQuery = new URLSearchParams({ action: agentAction, focus: selectedNode?.id ?? '' })
    const stream = new EventSource(`/api/agent-runs/${encodeURIComponent(runId)}/events?${streamQuery.toString()}`)
    streamRef.current = stream
    const handleEvent = (event: Event) => {
      try {
        const payload = JSON.parse((event as MessageEvent<string>).data) as Record<string, unknown>
        const normalized = normalizeStreamPayload(payload, event.type, runId)
        if (normalized) setFeed((current) => addEvent(current, normalized))
      } catch {
        // Ignore one malformed transport frame; the local fallback protects the evidence view.
      }
    }
    for (const eventName of ['agent.started', 'agent.narrative', 'agent.graph', 'agent.analytics', 'agent.revision', 'agent.critic', 'agent.progress', 'agent.tool_call', 'agent.tool_result', 'agent.message', 'agent.completed', 'agent.failed']) {
      stream.addEventListener(eventName, handleEvent)
    }
    const finish = () => {
      stream.close()
      setAgentRunning(false)
      if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current)
      fallbackTimerRef.current = null
    }
    stream.addEventListener('agent.done', finish)
    stream.onerror = () => {
      runLocalFallback()
      finish()
    }
    fallbackTimerRef.current = setTimeout(() => {
      setFeed((current) => {
        if (current.some((event) => event.stage === 'critic')) return current
        return createAgentEventStream(snapshot, { action: agentAction, prompt: agentPrompt, ...(selectedNode?.id ? { focusNode: selectedNode.id } : {}) })
          .map(toStreamEvent)
          .reduce((items, event) => addEvent(items, event), current)
      })
      finish()
    }, 3500)
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      setIndexOpen(false)
      setInspectorOpen(false)
      setAgentOpen(false)
      setGitOpen(false)
      return
    }
    if (event.key === ' ') {
      event.preventDefault()
      setTraceActive((value) => !value)
      return
    }
    if (!['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].includes(event.key)) return
    const index = activeGraph.nodes.findIndex((node) => node.id === selectedNode?.id)
    if (index < 0) return
    event.preventDefault()
    const delta = event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 1
    const next = activeGraph.nodes[(index + delta + activeGraph.nodes.length) % activeGraph.nodes.length]
    if (next) selectNode(next)
  }

  const sourceLabel = snapshot.dataSource.label
  const sourceClass = snapshot.dataSource.source

  return (
    <div className="fg-app fg-script-app" data-testid="workspace" data-hydrated={hydrated ? 'true' : 'false'} onKeyDown={handleKeyDown} tabIndex={-1}>
      <header className="fg-topbar">
        <div className="fg-brand-lockup">
          <span className="fg-brand">CLIO</span>
          <span className="fg-topline">CONTINUITY &amp; LINEAGE INTELLIGENCE OPERATOR</span>
        </div>
        <div className="fg-top-actions" aria-label="Workspace controls">
          <button type="button" className="fg-top-action" onClick={() => setOnboardingOpen(true)} aria-label="START guide">START</button>
          <button type="button" className="fg-top-action" onClick={() => {
            const next = !indexOpen
            setIndexOpen(next)
            if (next) {
              setInspectorOpen(false)
              setAgentOpen(false)
              setGitOpen(false)
            }
          }} aria-expanded={indexOpen} aria-controls="script-index">SCENES</button>
          <button type="button" className={`fg-top-action ${snapshot.scriptGit ? 'is-connected' : ''}`} onClick={openScriptGit} aria-label="SCRIPT GIT" aria-expanded={gitOpen} aria-controls="script-git-overlay">GIT{snapshot.scriptGit ? ` · ${snapshot.scriptGit.shortSha}` : ''}</button>
          <button type="button" className="fg-top-action" onClick={() => openAgent('inspect')} aria-label="AGENT">AGENT</button>
          <button type="button" className={`fg-top-action ${viewMode === 'overview' ? 'is-active' : ''}`} onClick={() => {
            setViewMode('overview')
            setTraceActive(true)
            setInspectorOpen(false)
            setAgentOpen(false)
            setGitOpen(false)
          }} aria-pressed={viewMode === 'overview'} aria-label="SCRIPT MAP">MAP</button>
          <button type="button" className={`fg-top-action ${viewMode === 'trace' ? 'is-active' : ''}`} onClick={() => {
            setViewMode('trace')
            setTraceActive(true)
            setInspectorOpen(false)
            setAgentOpen(false)
            setGitOpen(false)
          }} aria-pressed={viewMode === 'trace'} aria-label="TRACE PATH">TRACE</button>
          <button type="button" className="fg-top-action fg-top-action--accent" onClick={() => openCreateNode('scene')} aria-label="Create new scene">NEW</button>
        </div>
        <div className="fg-topmeta">
          <span className="fg-chip fg-chip--bright">LOCAL DEMO</span>
          <span className={`fg-chip fg-chip--${sourceClass}`}>{sourceLabel}</span>
          <span className="fg-chip fg-chip--simulation">LOCAL SIMULATION</span>
        </div>
      </header>

      <div className="fg-changebar" aria-label="Active revision V5: scene 47 changes from restaurant to moving car">
        <span className="fg-label">ACTIVE</span>
        <strong>V5 / SC 47 · RESTAURANT → MOVING CAR</strong>
          <span className="fg-changebar__right">
          <span>{snapshot.sceneCount} SCENES · {snapshot.beatCount} BEATS</span>
          <span className="fg-total-clock">{formatClock(snapshot.totalDurationSeconds)}</span>
        </span>
      </div>

      <main className="fg-workspace">
        <aside id="script-index" className={`fg-rail ${indexOpen ? 'is-open' : ''}`} aria-label="Script scenes" aria-hidden={!indexOpen}>
          <div className="fg-rail__head">
            <span className="fg-label">SCRIPT INDEX / {snapshot.sceneCount} SCENES</span>
            <button type="button" className="fg-overlay-close" onClick={() => setIndexOpen(false)} aria-label="Close script index">×</button>
          </div>
          <ol className="fg-stage-list fg-scene-list">
            {activeGraph.nodes.filter((node) => node.data.kind === 'scene').map((node) => (
              <li key={node.id} className={node.id === selectedNode?.id ? 'is-active' : ''}>
                <button
                  type="button"
                  aria-label={`SC ${node.data.sceneNumber ?? ''} · ${node.data.title}`}
                  onClick={() => selectNode(node)}
                >
                  <span className="fg-stage-index">{node.data.sceneNumber}</span>
                  <span className="fg-stage-name">{node.data.title}</span>
                  <span className={`fg-stage-state fg-stage-state--${node.data.status}`}>{nodeTime(node)} · {formatClock(node.data.durationSeconds ?? 0)}</span>
                </button>
              </li>
            ))}
          </ol>
          <div className="fg-rail__foot fg-script-index-foot">
            <span className="fg-label">PARENT = SCENE · CHILD = BEAT</span>
            <span>TEXT · NARRATION · TIME</span>
          </div>
        </aside>

        <section className="fg-canvas" aria-label="Script dependency graph" data-view-mode={viewMode}>
          <div className="fg-canvas__head">
            <div>
              <span className="fg-label">{viewMode === 'overview' ? 'SCRIPT MAP' : 'DEPENDENCY TRACE'}</span>
              <span className="fg-micro">{activeGraph.nodes.length} NODES · {activeGraph.edges.length} LINKS</span>
            </div>
            <div className="fg-canvas__controls">
              <button type="button" onClick={() => setTraceActive((value) => !value)} aria-pressed={traceActive}>{traceActive ? 'TRACE ON' : 'TRACE OFF'}</button>
              <button type="button" onClick={() => flowRef.current?.fitView({ duration: 0, padding: 0.1 })}>FIT</button>
            </div>
          </div>
          <ReactFlowProvider>
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onInit={(instance) => { flowRef.current = instance }}
              onNodeClick={(_, node) => {
                const target = activeGraph.nodes.find((item) => item.id === node.id)
                if (target) selectNode(target)
              }}
              fitView
              fitViewOptions={{ padding: 0.13, minZoom: 0.3, maxZoom: 1.2 }}
              minZoom={0.3}
              maxZoom={1.5}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              nodesFocusable
              panOnDrag
              zoomOnDoubleClick={false}
              className="fg-flow"
            />
          </ReactFlowProvider>
          <div className="fg-canvas__foot">
            <span>SCENE → BEAT · SCRIPT + NARRATION</span>
            <span>00:00 → {formatClock(snapshot.totalDurationSeconds)}</span>
          </div>
        </section>

        <aside className={`fg-inspector ${inspectorOpen ? 'is-open' : ''}`} aria-label="Context inspector" aria-hidden={!inspectorOpen} data-phase={phase}>
          <div className="fg-inspector__head">
            <span className="fg-label">{nodeRole(selectedNode)} / {phase.toUpperCase()}</span>
            <button type="button" className="fg-overlay-close" onClick={() => setInspectorOpen(false)} aria-label="Close inspector">×</button>
          </div>
          <section className="fg-inspector__hero">
            <span className="fg-kicker">{selectedNode?.data.sceneNumber ? `SCENE ${selectedNode.data.sceneNumber}` : 'ACTIVE REVISION'}</span>
            <h1>{selectedNode?.data.title}</h1>
            <p>{selectedNode?.data.detail}</p>
            <ProvenanceTag value={selectedNode?.data.provenance} />
          </section>
          <SceneInspector
            snapshot={snapshot}
            node={selectedNode}
            onAgent={openAgent}
            expandedSceneIds={expandedSceneIds}
            onToggleBeats={toggleBeats}
            onSelectNode={selectNode}
            onEditNode={openEditNode}
            onCreateScene={() => openCreateNode('scene')}
            onCreateBeat={(scene) => openCreateNode('beat', scene)}
            onDeleteNode={requestDeleteNode}
            crudError={crudError}
          />
        </aside>
      </main>

      {agentOpen ? (
        <AgentOverlay
          node={selectedNode}
          action={agentAction}
          prompt={agentPrompt}
          events={feed}
          running={agentRunning}
          onAction={chooseAgentAction}
          onPrompt={setAgentPrompt}
          onRun={() => void runAgent()}
          onClose={() => setAgentOpen(false)}
        />
      ) : null}
      {gitOpen ? <ScriptGitOverlay snapshot={snapshot} onApplied={() => void appliedScriptGit()} onClose={() => setGitOpen(false)} /> : null}
      {onboardingOpen ? <OnboardingOverlay onDone={finishOnboarding} onCreate={() => openCreateNode('scene')} /> : null}
      {editorOpen ? (
        <NodeEditorOverlay
          mode={editorMode}
          node={editorNodeId ? snapshot.graph.nodes.find((item) => item.id === editorNodeId) : undefined}
          defaultKind={editorDefaultKind}
          defaultParentId={editorDefaultParentId}
          scenes={snapshot.graph.nodes.filter((item) => item.data.kind === 'scene').sort((a, b) => Number(a.data.sceneNumber ?? 0) - Number(b.data.sceneNumber ?? 0))}
          saving={crudSaving}
          error={crudError}
          onSave={(draft) => void saveNode(draft)}
          onClose={() => setEditorOpen(false)}
        />
      ) : null}
      {deleteTarget ? (
        <section className="fg-delete-overlay" role="dialog" aria-modal="true" aria-label="Confirm node deletion">
          <div className="fg-delete-dialog">
            <span className="fg-label">DELETE NODE</span>
            <h2>{nodeName(deleteTarget)}</h2>
            <p>{deleteTarget.data.kind === 'scene' ? 'This also removes its child beats.' : 'This removes the beat and its links.'}</p>
            <div className="fg-delete-dialog__actions">
              <button type="button" className="fg-button-quiet" onClick={() => setDeleteTarget(undefined)}>CANCEL</button>
              <button type="button" className="fg-action fg-action--danger" onClick={() => void confirmDeleteNode()} disabled={crudSaving}>{crudSaving ? 'DELETING…' : 'DELETE'}</button>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  )
}

function toStreamEvent(event: AgentEvent): StreamEvent {
  const tone = event.tone === 'understood' ? 'trace' : event.tone === 'breaking' ? 'breach' : event.tone
  return { id: event.id, stage: event.phase, label: event.label, detail: event.detail, tone, at: event.createdAt.slice(11, 19) }
}

function toStreamEvents(events: AgentEvent[]): StreamEvent[] {
  return events.map(toStreamEvent)
}

function normalizeStreamPayload(payload: Record<string, unknown>, eventType: string, runId: string): StreamEvent | null {
  const nested = payload.payload && typeof payload.payload === 'object' ? payload.payload as Record<string, unknown> : {}
  const eventPhase = eventType.replace(/^agent\./, '')
  const phaseValue = typeof payload.phase === 'string' ? payload.phase : typeof nested.phase === 'string' ? nested.phase : eventPhase
  if (phaseValue === 'done' || phaseValue === 'started' || phaseValue === 'completed') return null
  const phase = ['narrative', 'graph', 'analytics', 'revision', 'critic'].includes(phaseValue) ? phaseValue : eventPhase
  const action = typeof nested.action === 'string' ? nested.action : ''
  const labels: Record<string, string> = {
    narrative: 'SCRIPT / READ',
    graph: 'GRAPH / TRACED',
    analytics: action === 'remove' ? 'TIME / REMOVED' : 'TIME / COMPUTED',
    revision: 'REVISION / V5',
    critic: 'CRITIC / PROPOSE',
  }
  const detail = typeof payload.detail === 'string'
    ? payload.detail
    : typeof nested.notes === 'string'
      ? nested.notes
      : typeof nested.assessment === 'string'
        ? nested.assessment
        : typeof payload.message === 'string' && !payload.message.startsWith('phase:')
          ? payload.message
          : `Provider phase ${phase}.`
  const tone: StreamEvent['tone'] = phase === 'graph' && (action === 'edit' || action === 'remove')
    ? 'breach'
    : phase === 'critic'
      ? 'pending'
      : 'trace'
  return {
    id: typeof payload.id === 'string' ? payload.id : `${runId}-${phase}-${Date.now()}`,
    stage: phase,
    label: labels[phase] ?? phase.toUpperCase(),
    detail,
    tone,
    at: new Date().toISOString().slice(11, 19),
  }
}

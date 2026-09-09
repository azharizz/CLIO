import { createFallbackSnapshot, formatClock, runtimeValue, setWorkspaceSnapshot, type WorkspaceSnapshot } from './workspace'
import { provenance } from './provenance'
import type { DeliveryVariant, PipelineStage, Provenance, ProvenanceSource, ApprovalDecision, RuntimeProposal, WorkflowEvent, WorkspaceEdge, WorkspaceNode, ScriptGitDocument, ScriptGitState, ScriptGitParsed, ScriptGitRevision } from './contracts'

/** The Python API is intentionally treated as an untrusted transport. */
export type BackendWorkspacePayload = {
  request?: { film_id?: string | null; revision_id?: string | null }
  workspace?: { delivery_count?: number; stage_count?: number }
  runtime?: { storage_mode?: string; runtime_mode?: string; mcp_enabled?: boolean; clickhouse_enabled?: boolean }
  query_source?: string
  provider_error?: { attempted_source?: string; fallback_source?: string; message?: string } | null
  pipeline_stages?: Array<{ name?: string; sequence?: number; description?: string }>
  graph_nodes?: Array<{
    id?: string
    kind?: string
    label?: string
    sequence?: number
    stage_name?: string
    status?: string
    scene_number?: string | number
    heading?: string
    script_text?: string
    narration_text?: string
    beat_number?: number | string
    parent_scene_id?: string
    start_seconds?: number
    end_seconds?: number
    duration_seconds?: number
    metadata?: Record<string, unknown>
    provenance?: Record<string, unknown>
  }>
  graph_edges?: Array<{ id?: string; source_id?: string; target_id?: string; relation?: string; metadata?: Record<string, unknown> | string; weight?: number; confidence?: number; provenance?: Record<string, unknown> }>
  workflows?: Array<{ id?: string; approval_status?: string; delivery_status?: string }>
  workflow_events?: Array<{ id?: string; workflow_id?: string; kind?: string; actor?: string; payload?: Record<string, unknown>; provenance?: Record<string, unknown>; occurred_at?: string }>
  delivery?: { ready?: Array<{ destination?: string; status?: string }>; delivered?: Array<{ destination?: string; status?: string }> }
  runtime_proposals?: Array<Record<string, unknown>>
  delivery_variants?: Array<Record<string, unknown>>
  delivery_conflicts?: Array<Record<string, unknown>>
  agent_runs?: Array<Record<string, unknown>>
  provenance?: { items?: Array<Record<string, unknown>> }
  script_git?: Record<string, unknown> | null
}

export class BackendUnavailableError extends Error {
  constructor(public readonly attemptedSource: string, message: string, public readonly status?: number, public readonly responseBody?: unknown) {
    super(message)
    this.name = 'BackendUnavailableError'
  }
}

export function backendBaseUrl(): string {
  const env = typeof process !== 'undefined' ? (process.env.CLIO_API_URL ?? process.env.FILMGRAPH_API_URL) : undefined
  return (env || 'http://127.0.0.1:8000').replace(/\/$/, '')
}

export async function backendFetch<T>(path: string, init?: RequestInit, timeoutMs = 1400): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${backendBaseUrl()}/api/v1${path}`, {
      ...init,
      signal: controller.signal,
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
    if (!response.ok) {
      let responseBody: unknown
      try { responseBody = await response.clone().json() } catch { responseBody = undefined }
      throw new BackendUnavailableError('python_fastapi', `FastAPI returned ${response.status}`, response.status, responseBody)
    }
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof BackendUnavailableError) throw error
    throw new BackendUnavailableError('python_fastapi', error instanceof Error ? error.message : 'FastAPI unavailable')
  } finally {
    clearTimeout(timeout)
  }
}

/** Preserve FastAPI's explicit transition conflicts at the same-origin edge. */
export function backendConflictResponse(error: unknown): Response | null {
  if (!(error instanceof BackendUnavailableError) || error.status !== 409) return null
  return Response.json(
    error.responseBody ?? { detail: { error_code: 'workflow.conflict', message: 'invalid workflow transition' } },
    { status: 409 },
  )
}

function sourceFor(payload: BackendWorkspacePayload) {
  if (payload.query_source === 'clickhouse_mcp') return provenance('clickhouse_mcp', 'CLICKHOUSE MCP', 'read-only graph query')
  if (payload.query_source === 'direct_clickhouse') return provenance('direct_clickhouse', 'DIRECT CLICKHOUSE', 'MCP unavailable; fallback path')
  if (payload.query_source === 'computed') return provenance('computed', 'LOCAL FALLBACK', 'memory repository; no ClickHouse provider available')
  if (payload.runtime?.mcp_enabled) return provenance('clickhouse_mcp', 'CLICKHOUSE MCP', 'read-only graph query')
  if (payload.runtime?.clickhouse_enabled || payload.runtime?.storage_mode === 'clickhouse') return provenance('direct_clickhouse', 'DIRECT CLICKHOUSE', 'MCP unavailable; fallback path')
  return provenance('computed', 'LOCAL FALLBACK', 'memory repository; no ClickHouse provider available')
}

function sourceKind(payload: BackendWorkspacePayload): ProvenanceSource {
  return sourceFor(payload).source
}

function normalizeGitParsed(value: unknown): ScriptGitParsed {
  const row = asRecord(value)
  return {
    sceneCount: numberValue(row?.scene_count ?? row?.sceneCount) ?? 0,
    beatCount: numberValue(row?.beat_count ?? row?.beatCount) ?? 0,
    durationSeconds: numberValue(row?.duration_seconds ?? row?.durationSeconds) ?? 0,
    timingEstimated: Boolean(row?.timing_estimated ?? row?.timingEstimated),
  }
}

function normalizeGitRevision(value: unknown): ScriptGitRevision | null {
  const row = asRecord(value)
  const sha = stringValue(row?.sha)
  if (!sha) return null
  const committedAt = stringValue(row?.committed_at ?? row?.committedAt)
  const htmlUrl = stringValue(row?.html_url ?? row?.htmlUrl)
  return {
    sha,
    shortSha: stringValue(row?.short_sha ?? row?.shortSha) ?? sha.slice(0, 8),
    message: stringValue(row?.message) ?? 'GitHub revision',
    author: stringValue(row?.author) ?? 'unknown',
    ...(committedAt ? { committedAt } : {}),
    ...(htmlUrl ? { htmlUrl } : {}),
    ...(row?.selected !== undefined ? { selected: Boolean(row.selected) } : {}),
  }
}

function normalizeGitState(value: unknown): ScriptGitState | undefined {
  const row = asRecord(value)
  if (!row || stringValue(row.source) !== 'github') return undefined
  const parsed = normalizeGitParsed(row.parsed)
  const revisions = Array.isArray(row.revisions)
    ? row.revisions.map(normalizeGitRevision).filter((item): item is ScriptGitRevision => item !== null)
    : []
  const sha = stringValue(row.sha) ?? revisions.find((item) => item.selected)?.sha ?? ''
  const repository = stringValue(row.repository)
  const path = stringValue(row.path)
  if (!sha || !repository || !path) return undefined
  const htmlUrl = stringValue(row.html_url ?? row.htmlUrl)
  const rawUrl = stringValue(row.raw_url ?? row.rawUrl)
  const size = numberValue(row.size)
  const message = stringValue(row.message)
  return {
    source: 'github',
    repository,
    owner: stringValue(row.owner) ?? repository.split('/')[0] ?? '',
    repo: stringValue(row.repo) ?? repository.split('/')[1] ?? '',
    path,
    ref: stringValue(row.ref) ?? 'main',
    sha,
    shortSha: stringValue(row.short_sha ?? row.shortSha) ?? sha.slice(0, 8),
    ...(htmlUrl ? { htmlUrl } : {}),
    ...(rawUrl ? { rawUrl } : {}),
    ...(size !== undefined ? { size } : {}),
    ...(message ? { message } : {}),
    parsed,
    revisions,
    provenance: provenanceFromRemote(asRecord(row.provenance), provenance('computed', 'GITHUB')),
  }
}

/** Normalize the GitHub loader's relational rows into the visual node contract. */
export function normalizeScriptGitDocument(value: Record<string, unknown>): ScriptGitDocument {
  const state = normalizeGitState(value)
  if (!state) throw new Error('GitHub response did not include a valid script source.')
  const rows = Array.isArray(value.nodes) ? value.nodes.map(asRecord).filter((item): item is Record<string, unknown> => Boolean(item)) : []
  const edgeRows = Array.isArray(value.edges) ? value.edges.map(asRecord).filter((item): item is Record<string, unknown> => Boolean(item)) : []
  const oldToNew = new Map<string, string>()
  const sourceRow = rows.find((row) => row.kind === 'script')
  const revisionNode: WorkspaceNode = {
    id: `revision-git-${state.shortSha}`,
    position: { x: 24, y: 285 },
    data: {
      kind: 'revision', stage: 'Script', eyebrow: 'REVISION / GITHUB', title: `${state.shortSha} · ${state.repository}`,
      code: state.ref, metric: `${state.parsed.sceneCount} SCENES`, secondary: 'GITHUB', status: 'understood',
      detail: state.message ?? `Loaded ${state.path} from GitHub.`, scriptText: stringValue(sourceRow?.script_text) ?? state.message,
      currentScriptText: stringValue(sourceRow?.script_text) ?? state.message,
      provenance: state.provenance, entityType: 'revision', scope: 'revision',
    },
  }
  if (sourceRow?.id) oldToNew.set(String(sourceRow.id), revisionNode.id)
  const sceneRows = rows.filter((row) => row.kind === 'scene').sort((a, b) => (numberValue(a.sequence) ?? 0) - (numberValue(b.sequence) ?? 0))
  const nodes: WorkspaceNode[] = [revisionNode]
  sceneRows.forEach((row, index) => {
    const id = `git-scene-${stringValue(row.scene_number) ?? String(index + 1)}-${state.shortSha}`
    oldToNew.set(String(row.id ?? id), id)
    const sceneNumber = stringValue(row.scene_number) ?? String(index + 1)
    const start = numberValue(row.start_seconds) ?? 0
    const end = numberValue(row.end_seconds) ?? start + 1
    const duration = numberValue(row.duration_seconds) ?? Math.max(1, end - start)
    const metadata = asRecord(row.metadata) ?? {}
    nodes.push({
      id,
      position: { x: 250 + (index % 4) * 285, y: 120 + Math.floor(index / 4) * 245 },
      data: {
        kind: 'scene', stage: 'Script', stageIndex: numberValue(row.sequence) ?? index + 1, sceneNumber,
        eyebrow: `SC ${sceneNumber}`, title: stringValue(row.heading ?? row.label) ?? `SCENE ${sceneNumber}`,
        code: `${formatClock(start)} → ${formatClock(end)}`, metric: formatClock(duration),
        secondary: `B${String(numberValue(metadata.child_count ?? metadata.childCount) ?? 0).padStart(2, '0')}`,
        status: ['breaking', 'pending', 'resolved', 'understood'].includes(String(row.status)) ? String(row.status) as WorkspaceNode['data']['status'] : 'understood',
        detail: stringValue(row.script_text ?? row.label), scriptText: stringValue(row.script_text ?? row.label),
        narrationText: stringValue(row.narration_text ?? metadata.narration_text ?? metadata.narration),
        childCount: numberValue(metadata.child_count ?? metadata.childCount) ?? 0,
        startSeconds: start, endSeconds: end, durationSeconds: duration, provenance: state.provenance,
        entityType: 'scene', scope: 'film',
      },
    })
  })
  const beatRows = rows.filter((row) => row.kind === 'beat' || row.kind === 'story_beat').sort((a, b) => (numberValue(a.sequence) ?? 0) - (numberValue(b.sequence) ?? 0))
  beatRows.forEach((row) => {
    const sceneNumber = stringValue(row.scene_number) ?? '—'
    const beatNumber = numberValue(row.beat_number) ?? 1
    const id = `git-beat-${sceneNumber}-${beatNumber}-${state.shortSha}`
    oldToNew.set(String(row.id ?? id), id)
    const parentId = row.parent_scene_id ? oldToNew.get(String(row.parent_scene_id)) : undefined
    const parent = parentId ? nodes.find((item) => item.id === parentId) : undefined
    const start = numberValue(row.start_seconds) ?? parent?.data.startSeconds ?? 0
    const end = numberValue(row.end_seconds) ?? parent?.data.endSeconds ?? start + 1
    const metadata = asRecord(row.metadata) ?? {}
    nodes.push({
      id,
      position: { x: (parent?.position.x ?? 250) + (beatNumber - 1) * 195, y: (parent?.position.y ?? 120) + 132 },
      data: {
        kind: 'beat', stage: 'Script', stageIndex: numberValue(row.sequence) ?? nodes.length, sceneNumber, beatNumber,
        parentSceneId: parentId, eyebrow: `SC ${sceneNumber} / B${String(beatNumber).padStart(2, '0')}`,
        title: stringValue(row.heading ?? row.label) ?? `BEAT ${beatNumber}`, code: `${formatClock(start)} → ${formatClock(end)}`,
        metric: formatClock(end - start), secondary: 'BEAT', status: parent?.data.status ?? 'understood',
        detail: stringValue(row.script_text ?? row.label), scriptText: stringValue(row.script_text ?? row.label),
        narrationText: stringValue(row.narration_text ?? metadata.narration_text ?? metadata.narration),
        startSeconds: start, endSeconds: end, durationSeconds: Math.max(1, end - start), provenance: state.provenance,
        entityType: 'beat', scope: 'beat',
      },
    })
  })
  const edges: WorkspaceEdge[] = edgeRows.flatMap((row, index) => {
    const source = row.source_id ? oldToNew.get(String(row.source_id)) : undefined
    const target = row.target_id ? oldToNew.get(String(row.target_id)) : undefined
    if (!source || !target) return []
    const metadata = typeof row.metadata === 'string' ? safeJsonRecord(row.metadata) : asRecord(row.metadata) ?? {}
    const relation = stringValue(row.relation) ?? 'follows'
    const kind = relation === 'contains' || metadata.kind === 'beat' ? 'beat' : 'backbone'
    const tone = ['breaking', 'pending', 'resolved', 'split', 'understood'].includes(String(metadata.tone)) ? String(metadata.tone) as WorkspaceEdge['data']['tone'] : 'understood'
    return [{ id: `git-edge-${index}-${state.shortSha}`, source, target, data: { relation, tone, kind, branch: 'backbone', provenance: state.provenance } }]
  })
  const contentHash = stringValue(value.content_hash ?? value.contentHash)
  return {
    ...state,
    content: String(value.content ?? ''),
    revisionId: stringValue(value.revision_id ?? value.revisionId) ?? `git-${state.shortSha}`,
    ...(contentHash ? { contentHash } : {}),
    nodes,
    edges,
  }
}

export async function loadScriptGit(source: string, ref?: string, path?: string): Promise<ScriptGitDocument> {
  const response = await fetch('/api/script-git/load', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, ...(ref ? { ref } : {}), ...(path ? { path } : {}), history_limit: 12 }),
  })
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>
  if (!response.ok) {
    const detail = asRecord(payload.detail)
    throw new Error(stringValue(detail?.message) ?? stringValue(payload.message) ?? `GitHub load failed (${response.status})`)
  }
  return normalizeScriptGitDocument(payload)
}

/** Normalize the API's relational response into the graph's visual contract. */
export function normalizeWorkspacePayload(payload: BackendWorkspacePayload, fallback = createFallbackSnapshot()): WorkspaceSnapshot {
  const next = structuredClone(fallback)
  const baseSource = sourceFor(payload)
  const dataSource = payload.provider_error?.message
    ? { ...baseSource, detail: `${baseSource.detail ?? ''} · ${payload.provider_error.message}`.replace(/^ · /, '') }
    : baseSource
  next.dataSource = dataSource
  next.runtimeMode = payload.runtime?.runtime_mode === 'live' ? 'live' : 'simulation'
  if (payload.provider_error?.message) {
    next.providerError = {
      attemptedSource: payload.provider_error.attempted_source ?? 'clickhouse_mcp',
      fallbackSource: payload.provider_error.fallback_source ?? 'computed',
      message: payload.provider_error.message,
    }
  }
  if (payload.request?.film_id) next.filmId = payload.request.film_id
  if (payload.request?.revision_id) next.revisionId = payload.request.revision_id
  const gitState = normalizeGitState(payload.script_git)
  if (gitState) next.scriptGit = gitState
  const remoteWorkflowId = payload.workflows?.[0]?.id
  if (remoteWorkflowId) next.workspaceId = remoteWorkflowId
  const remoteNodes = [...(payload.graph_nodes ?? [])].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0))
  const remoteScenes = remoteNodes.filter((node) => node.kind === 'scene')
  const remoteBeats = remoteNodes.filter((node) => node.kind === 'beat' || node.kind === 'story_beat')
  const remoteScript = remoteNodes.find((node) => node.kind === 'script')
  const sceneNodes = next.graph.nodes.filter((node) => node.data.kind === 'scene')
  const beatNodes = next.graph.nodes.filter((node) => node.data.kind === 'beat')
  const numberFor = (node: typeof remoteNodes[number]) => {
    const value = node.scene_number ?? node.metadata?.scene_number ?? node.metadata?.sceneNumber
    return value === undefined || value === null ? undefined : String(value).replace(/^SC\s*/i, '')
  }
  const numberIndex = new Map(remoteScenes.map((node, index) => [numberFor(node) ?? String(index), node] as const))
  const beatKeyFor = (node: typeof remoteNodes[number]) => {
    const scene = numberFor(node) ?? stringValue(node.metadata?.scene_number) ?? stringValue(node.metadata?.sceneNumber)
    const beat = node.beat_number ?? node.metadata?.beat_number ?? node.metadata?.beatNumber
    return scene && beat !== undefined && beat !== null ? `${scene}:${String(beat)}` : undefined
  }
  const beatIndex = new Map(remoteBeats.map((node) => [beatKeyFor(node), node] as const).filter(([key]) => Boolean(key)))
  const remoteToVisual = new Map<string, string>()
  if (remoteScript?.id) remoteToVisual.set(String(remoteScript.id), 'revision-v5')
  for (const scene of remoteScenes) {
    const visual = sceneNodes.find((item) => item.data.sceneNumber === numberFor(scene))
    if (visual && scene.id) remoteToVisual.set(String(scene.id), visual.id)
  }
  for (const beat of remoteBeats) {
    const key = beatKeyFor(beat)
    const visual = key ? beatNodes.find((item) => `${item.data.sceneNumber}:${item.data.beatNumber}` === key) : undefined
    if (visual && beat.id) remoteToVisual.set(String(beat.id), visual.id)
  }
  for (const visualNode of next.graph.nodes) {
    visualNode.data.provenance = provenance(sourceKind(payload), dataSource.label)
    if (visualNode.data.kind === 'revision' && remoteScript) {
      const text = remoteScript.script_text ?? stringValue(remoteScript.metadata?.script_text) ?? remoteScript.label
      visualNode.data.scriptText = text
      visualNode.data.currentScriptText = text
      visualNode.data.status = remoteScript.status === 'breaking' ? 'breaking' : visualNode.data.status
      continue
    }
    if (visualNode.data.kind === 'beat') {
      const remote = beatIndex.get(`${visualNode.data.sceneNumber}:${visualNode.data.beatNumber}`)
      if (!remote) continue
      const start = numberValue(remote.start_seconds ?? remote.metadata?.start_seconds)
      const end = numberValue(remote.end_seconds ?? remote.metadata?.end_seconds)
      const duration = numberValue(remote.duration_seconds ?? remote.metadata?.duration_seconds)
        ?? (start !== undefined && end !== undefined ? end - start : undefined)
      const text = remote.script_text ?? stringValue(remote.metadata?.script_text)
      const narration = remote.narration_text ?? stringValue(remote.metadata?.narration_text) ?? stringValue(remote.metadata?.narration)
      const parent = sceneNodes.find((item) => item.data.sceneNumber === visualNode.data.sceneNumber)
      if (remote.heading || remote.label) visualNode.data.title = remote.heading ?? remote.label ?? visualNode.data.title
      if (text) {
        visualNode.data.scriptText = text
        visualNode.data.detail = text
      }
      if (Object.prototype.hasOwnProperty.call(remote, 'narration_text') || remote.metadata?.narration_text !== undefined || remote.metadata?.narration !== undefined) {
        visualNode.data.narrationText = narration
      }
      if (parent) visualNode.data.parentSceneId = parent.id
      const remoteBeatNumber = numberValue(remote.beat_number ?? remote.metadata?.beat_number ?? remote.metadata?.beatNumber)
      if (remoteBeatNumber !== undefined) visualNode.data.beatNumber = remoteBeatNumber
      if (start !== undefined) visualNode.data.startSeconds = start
      if (end !== undefined) visualNode.data.endSeconds = end
      if (duration !== undefined) {
        visualNode.data.durationSeconds = duration
        visualNode.data.metric = formatClock(duration)
      }
      if (remote.status === 'breaking' || remote.status === 'pending' || remote.status === 'resolved' || remote.status === 'understood') {
        visualNode.data.status = remote.status
      }
      continue
    }
    if (visualNode.data.kind !== 'scene') continue
    const remote = numberIndex.get(visualNode.data.sceneNumber ?? '')
      ?? remoteScenes[sceneNodes.indexOf(visualNode)]
    if (!remote) continue
    const start = numberValue(remote.start_seconds ?? remote.metadata?.start_seconds)
    const end = numberValue(remote.end_seconds ?? remote.metadata?.end_seconds)
    const duration = numberValue(remote.duration_seconds ?? remote.metadata?.duration_seconds)
      ?? (start !== undefined && end !== undefined ? end - start : undefined)
    const text = remote.script_text ?? stringValue(remote.metadata?.script_text)
    const narration = remote.narration_text ?? stringValue(remote.metadata?.narration_text) ?? stringValue(remote.metadata?.narration)
    if (remote.heading || remote.label) visualNode.data.title = remote.heading ?? remote.label ?? visualNode.data.title
    if (text) {
      visualNode.data.scriptText = text
      visualNode.data.detail = text
    }
    if (Object.prototype.hasOwnProperty.call(remote, 'narration_text') || remote.metadata?.narration_text !== undefined || remote.metadata?.narration !== undefined) {
      visualNode.data.narrationText = narration
    }
    const childCount = numberValue(remote.metadata?.child_count ?? remote.metadata?.childCount)
    if (childCount !== undefined) visualNode.data.childCount = childCount
    if (start !== undefined) visualNode.data.startSeconds = start
    if (end !== undefined) visualNode.data.endSeconds = end
    if (duration !== undefined) {
      visualNode.data.durationSeconds = duration
      visualNode.data.metric = formatClock(duration)
    }
    if (remote.status === 'breaking' || remote.status === 'pending' || remote.status === 'resolved' || remote.status === 'understood') {
      visualNode.data.status = remote.status
    }
  }
  // A current relational response is authoritative for script nodes.  Add
  // newly-created scenes/beats using their server IDs and remove deleted
  // seeded rows, while retaining the richer fallback graph for partial/legacy
  // responses (for example a one-row fake MCP contract test).
  const authoritativeScript = remoteScenes.length >= 2 || remoteBeats.length > 0
  if (authoritativeScript) {
    const existingVisualIds = new Set(next.graph.nodes.map((item) => item.id))
    const sceneVisuals = next.graph.nodes.filter((item) => item.data.kind === 'scene')
    for (const remote of remoteScenes) {
      if (!remote.id || remoteToVisual.has(String(remote.id))) continue
      const sceneNumber = numberFor(remote) ?? String(sceneVisuals.length + 42)
      const start = numberValue(remote.start_seconds ?? remote.metadata?.start_seconds) ?? 0
      const end = numberValue(remote.end_seconds ?? remote.metadata?.end_seconds) ?? start + 1
      const count = numberValue(remote.metadata?.child_count ?? remote.metadata?.childCount) ?? 0
      const title = remote.heading ?? remote.label ?? `SC ${sceneNumber}`
      const text = remote.script_text ?? stringValue(remote.metadata?.script_text) ?? title
      const dynamic: WorkspaceNode = {
        id: String(remote.id),
        position: { x: 250 + (sceneVisuals.length % 4) * 285, y: 120 + Math.floor(sceneVisuals.length / 4) * 245 },
        data: {
          kind: 'scene', stage: 'Script', stageIndex: remote.sequence ?? sceneVisuals.length + 1, sceneNumber,
          eyebrow: `SC ${sceneNumber}`, title, code: `${formatClock(start)} → ${formatClock(end)}`,
          metric: formatClock(end - start), secondary: `B${String(count).padStart(2, '0')}`,
          status: (remote.status === 'breaking' || remote.status === 'pending' || remote.status === 'resolved' || remote.status === 'understood') ? remote.status : 'pending',
          detail: text, scriptText: text,
          narrationText: remote.narration_text ?? stringValue(remote.metadata?.narration_text) ?? stringValue(remote.metadata?.narration),
          childCount: count, startSeconds: start, endSeconds: end, durationSeconds: end - start,
          provenance: dataSource, entityType: 'scene', scope: 'film',
        },
      }
      next.graph.nodes.push(dynamic)
      sceneVisuals.push(dynamic)
      remoteToVisual.set(String(remote.id), dynamic.id)
      existingVisualIds.add(dynamic.id)
    }
    const currentVisualIds = new Set<string>()
    for (const remote of remoteNodes) {
      const mapped = remote.id ? remoteToVisual.get(String(remote.id)) : undefined
      if (mapped) currentVisualIds.add(mapped)
    }
    next.graph.nodes = next.graph.nodes.filter((item) => {
      if (item.data.kind === 'revision') return Boolean(remoteScript)
      if (item.data.kind === 'scene' || item.data.kind === 'beat') return currentVisualIds.has(item.id)
      return true
    })
    for (const remote of remoteBeats) {
      if (!remote.id || remoteToVisual.has(String(remote.id))) continue
      const parentRef = remote.parent_scene_id ?? stringValue(remote.metadata?.parent_scene_id)
      const parentId = parentRef ? remoteToVisual.get(String(parentRef)) ?? parentRef : undefined
      const parent = parentId ? next.graph.nodes.find((item) => item.id === parentId && item.data.kind === 'scene') : undefined
      const sceneNumber = numberFor(remote) ?? parent?.data.sceneNumber ?? '—'
      const beatNumber = numberValue(remote.beat_number ?? remote.metadata?.beat_number ?? remote.metadata?.beatNumber) ?? 1
      const start = numberValue(remote.start_seconds ?? remote.metadata?.start_seconds) ?? parent?.data.startSeconds ?? 0
      const end = numberValue(remote.end_seconds ?? remote.metadata?.end_seconds) ?? parent?.data.endSeconds ?? start + 1
      const title = remote.heading ?? remote.label ?? `BEAT ${beatNumber}`
      const text = remote.script_text ?? stringValue(remote.metadata?.script_text) ?? title
      const dynamic: WorkspaceNode = {
        id: String(remote.id),
        position: { x: (parent?.position.x ?? 250) + (beatNumber - 1) * 195, y: (parent?.position.y ?? 120) + 132 },
        data: {
          kind: 'beat', stage: 'Script', stageIndex: remote.sequence ?? next.graph.nodes.length + 1, sceneNumber,
          beatNumber, parentSceneId: parent?.id ?? parentId, eyebrow: `SC ${sceneNumber} / B${String(beatNumber).padStart(2, '0')}`,
          title, code: `${formatClock(start)} → ${formatClock(end)}`, metric: formatClock(end - start), secondary: 'BEAT',
          status: (remote.status === 'breaking' || remote.status === 'pending' || remote.status === 'resolved' || remote.status === 'understood') ? remote.status : parent?.data.status ?? 'pending',
          detail: text, scriptText: text,
          narrationText: remote.narration_text ?? stringValue(remote.metadata?.narration_text) ?? stringValue(remote.metadata?.narration),
          startSeconds: start, endSeconds: end, durationSeconds: end - start, provenance: dataSource,
          entityType: 'beat', scope: 'beat',
        },
      }
      next.graph.nodes.push(dynamic)
      remoteToVisual.set(String(remote.id), dynamic.id)
    }
  }
  const timedEnds = next.graph.nodes.filter((node) => node.data.kind === 'scene').map((node) => node.data.endSeconds ?? 0)
  if (remoteScenes.length) next.sceneCount = remoteScenes.length
  if (remoteBeats.length) next.beatCount = remoteBeats.length
  else next.beatCount = beatNodes.length
  // Child counts are a convenience badge, not a second source of truth. When
  // a relational response is authoritative, derive them from the beat rows
  // so a create/delete remains accurate even if an older database has stale
  // denormalized metadata on its parent scene.
  if (authoritativeScript && remoteBeats.length > 0) {
    const counts = new Map<string, number>()
    for (const beat of remoteBeats) {
      const scene = numberFor(beat)
      if (scene) counts.set(scene, (counts.get(scene) ?? 0) + 1)
    }
    for (const scene of next.graph.nodes.filter((node) => node.data.kind === 'scene')) {
      const count = counts.get(scene.data.sceneNumber ?? '') ?? 0
      scene.data.childCount = count
      scene.data.secondary = scene.data.sceneNumber === '47' && scene.data.status === 'breaking'
        ? `CHANGED · B${String(count).padStart(2, '0')}`
        : `B${String(count).padStart(2, '0')}`
    }
  }
  if (timedEnds.some((value) => value > 0)) next.totalDurationSeconds = Math.max(...timedEnds)
  next.deliveryCount = 0
  // Runtime surgery and delivery packages are deliberately deferred from the
  // script-first slice.  Ignore stale catalog rows if an older ClickHouse
  // database is still running beside the app.
  next.runtimeProposals = []
  next.deliveryVariants = []

  // Keep the richer branch nodes in the visual contract even when the direct
  // relational query only returns the ten canonical backbone entities.
  const remoteEdges = payload.graph_edges ?? []
  if (authoritativeScript && remoteEdges.length > 0) {
    const mappedEdges = remoteEdges.flatMap((remote, index) => {
      const source = remote.source_id ? remoteToVisual.get(String(remote.source_id)) : undefined
      const target = remote.target_id ? remoteToVisual.get(String(remote.target_id)) : undefined
      if (!source || !target) return []
      const metadata = typeof remote.metadata === 'string' ? safeJsonRecord(remote.metadata) : (remote.metadata ?? {})
      const relation = remote.relation ?? 'follows'
      const kind = metadata.kind === 'beat' || relation === 'contains' || (source.startsWith('beat-') && target.startsWith('beat-')) ? 'beat' : 'backbone'
      const tone = metadata.tone === 'breaking' || metadata.tone === 'pending' || metadata.tone === 'resolved' || metadata.tone === 'split' ? metadata.tone : 'understood'
      return [{
        id: String(remote.id ?? `remote-edge-${index}`), source, target,
        data: { relation, tone, kind, branch: kind === 'beat' ? 'backbone' : 'backbone', provenance: dataSource },
      } as WorkspaceEdge]
    })
    if (mappedEdges.length > 0) next.graph.edges = mappedEdges
  } else {
    next.graph.edges = next.graph.edges.map((item) => ({ ...item, data: { ...item.data, provenance: dataSource } }))
  }
  next.graph.nodes = next.graph.nodes.map((item) => ({ ...item, data: { ...item.data, provenance: item.data.provenance ?? dataSource } }))

  // A GitHub import is a new script map, not a partial overlay on the demo
  // revision. Keep its identity visible and make the source node the first
  // keyboard/selection target after a refresh.
  if (gitState) {
    next.revisionLabel = `${gitState.shortSha} · GITHUB`
    next.changedScene = `${gitState.repository} · ${gitState.path}`
    next.revisionBefore = 'Previous GitHub commit'
    next.revisionAfter = gitState.message ?? `Loaded ${gitState.path}`
    next.sceneCount = gitState.parsed.sceneCount || next.sceneCount
    next.beatCount = gitState.parsed.beatCount || next.beatCount
    next.totalDurationSeconds = gitState.parsed.durationSeconds || next.totalDurationSeconds
    next.currentRuntime = runtimeValue(next.totalDurationSeconds)
    next.targetRuntime = runtimeValue(next.totalDurationSeconds)
    const preferred = next.graph.nodes.find((node) => node.data.kind === 'revision')
      ?? next.graph.nodes.find((node) => node.data.kind === 'scene')
    if (preferred) next.selectedNodeId = preferred.id
  } else if (!next.graph.nodes.some((node) => node.id === next.selectedNodeId)) {
    next.selectedNodeId = next.graph.nodes.find((node) => node.data.kind === 'revision')?.id
      ?? next.graph.nodes.find((node) => node.data.kind === 'scene')?.id
      ?? ''
  }

  // Relational catalog rows are normalized into the same compact visual
  // contract as the local seed.  The UI keeps stable slugs so graph nodes and
  // human approval controls remain addressable across MCP/direct refreshes.
  const remoteEvents = (payload.workflow_events ?? []).filter((event) => !/(delivery|runtime|master|localization)/i.test(event.kind ?? ''))
  next.workflowEvents = remoteEvents.length > 0
    ? remoteEvents.map((event, index) => ({
        eventType: event.kind ?? 'workflow.snapshot',
        workflowId: event.workflow_id ?? next.workspaceId,
        actor: event.actor ?? 'SYSTEM',
        payload: primitivePayload(event.payload),
        provenance: provenanceFromRemote(event.provenance, dataSource),
        createdAt: event.occurred_at ?? new Date().toISOString(),
      }))
      .filter((event, index, list) => Boolean(event.workflowId) && list.findIndex((candidate) => candidate.eventType === event.eventType && candidate.createdAt === event.createdAt && candidate.workflowId === event.workflowId) === index)
    : (payload.workflows ?? []).map((workflow, index) => ({
        eventType: 'workflow.snapshot',
        workflowId: workflow.id ?? `remote-${index}`,
        actor: 'SYSTEM',
        payload: {
          ...(workflow.approval_status ? { approval_status: workflow.approval_status } : {}),
          ...(workflow.delivery_status ? { delivery_status: workflow.delivery_status } : {}),
        },
        provenance: dataSource,
        createdAt: new Date().toISOString(),
      }))
  next.approvals = approvalsFromEvents(next.workflowEvents)
  replayWorkflowState(next)
  return next
}

function normalizeRemoteProposal(row: Record<string, unknown>, index: number, fallback: Provenance): RuntimeProposal {
  const label = stringValue(row.label) ?? `PROPOSAL ${String(index + 1).padStart(2, '0')}`
  const isCut = /cut\s*sc\s*47/i.test(label)
  const deltaSeconds = numberValue(row.delta_seconds) ?? numberValue(row.deltaSeconds) ?? (isCut ? -240 : 0)
  const resultSeconds = numberValue(row.result_seconds) ?? numberValue(row.resultSeconds) ?? (isCut ? 7440 : 7680)
  const confidence = numberValue(row.confidence)
  return {
    id: isCut ? 'cut-sc47' : /reshoot/i.test(label) ? 'reshoot-vehicle' : `proposal-${index + 1}`,
    label,
    deltaMinutes: Math.round(deltaSeconds / 60),
    resultMinutes: Math.round(resultSeconds / 60),
    costDelta: stringValue(row.cost_delta) ?? stringValue(row.costDelta) ?? 'ESTIMATE',
    confidence: confidence === undefined ? '~—' : `~${confidence.toFixed(2)}`,
    recommendation: Boolean(row.recommended ?? row.recommendation ?? isCut),
    provenance: provenanceFromRemote(asRecord(row.provenance), fallback),
    ...(Boolean(row.selected) ? { selected: true } : {}),
  }
}

function normalizeRemoteVariant(row: Record<string, unknown>, index: number, fallback: Provenance): DeliveryVariant {
  const platform = stringValue(row.platform) ?? 'STREAM'
  const territory = stringValue(row.territory) ?? 'US'
  const slug = variantSlug(platform, territory, index)
  const rawStatus = stringValue(row.status)?.toLowerCase()
  const status: DeliveryVariant['status'] = rawStatus === 'approved' ? 'approved' : rawStatus === 'conflict' ? 'conflict' : 'ready'
  const runtimeSeconds = numberValue(row.runtime_seconds) ?? numberValue(row.runtimeSeconds) ?? 7440
  const conflict = stringValue(row.conflict)
  return {
    id: slug,
    platform,
    territory,
    audio: stringValue(row.audio) ?? 'EN 5.1',
    subtitle: stringValue(row.subtitle) ?? 'EN CC',
    runtime: Math.round(runtimeSeconds / 60),
    status,
    ...(conflict ? { conflict } : {}),
    provenance: provenanceFromRemote(asRecord(row.provenance), fallback),
  }
}

function variantSlug(platform: string, territory: string, index: number): string {
  const known: Record<string, string> = {
    'stream-us': 'netflix-us',
    'airline-kor': 'airline-kor',
    'broadcast-deu': 'broadcast-deu',
    'stream-jpn': 'stream-jpn',
    'airline-us': 'airline-us',
    'broadcast-kor': 'broadcast-kor',
  }
  const key = `${platform}-${territory}`.toLowerCase()
  return known[key] ?? `${key}-${index + 1}`
}

function variantMatchesRemoteId(visualId: string, remoteId: unknown): boolean {
  if (typeof remoteId !== 'string') return false
  const normalized = remoteId.toLowerCase().replace(/^variant-/, '')
  return visualId.toLowerCase() === normalized || visualId.toLowerCase().endsWith(normalized)
}

function numberValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : undefined
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' ? value as Record<string, unknown> : undefined
}

function safeJsonRecord(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value)
    return asRecord(parsed) ?? {}
  } catch {
    return {}
  }
}

/** Rebuild mutable UI state from append-only events after a refresh. */
function replayWorkflowState(snapshot: WorkspaceSnapshot) {
  for (const event of snapshot.workflowEvents) {
    if (!['script.node.approved', 'script.node.held', 'workflow.approved', 'workflow.rejected'].includes(event.eventType)) continue
    const nodeId = stringValue(event.payload.nodeId) ?? stringValue(event.payload.node_id)
    const node = nodeId
      ? snapshot.graph.nodes.find((item) => item.id === nodeId)
      : undefined
    if (!node) continue
    node.data.status = event.eventType.endsWith('approved') ? 'resolved' : 'pending'
    node.data.selectedAction = event.eventType.endsWith('approved')
  }
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined
}

function primitivePayload(value: Record<string, unknown> | undefined): Record<string, string | number | boolean | null> {
  if (!value) return {}
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean' || item === null ? item : JSON.stringify(item)]))
}

function provenanceFromRemote(value: Record<string, unknown> | undefined, fallback: ReturnType<typeof provenance>) {
  const source = value?.source
  const allowed: ProvenanceSource[] = ['direct_clickhouse', 'clickhouse_mcp', 'agent_simulation', 'gemini_adk', 'computed', 'estimate']
  return provenance(allowed.includes(source as ProvenanceSource) ? source as ProvenanceSource : fallback.source, typeof value?.label === 'string' ? value.label : fallback.label, typeof value?.detail === 'string' ? value.detail : fallback.detail)
}

function approvalsFromEvents(events: WorkflowEvent[]) {
  return events.flatMap((event, index) => {
    const decision = event.eventType === 'workflow.approved' || event.eventType === 'editorial.resolution.approved' ? 'approve' : event.eventType === 'workflow.rejected' || event.eventType.endsWith('.decision.held') || event.eventType === 'delivery.variant.held' ? 'hold' : null
    if (!decision) return []
    const isDelivery = event.eventType.startsWith('delivery.') || event.eventType === 'workflow.delivered' || typeof event.payload.variantId === 'string' || typeof event.payload.variant_id === 'string'
    return [{ id: `remote-approval-${index}`, decision: decision as ApprovalDecision, target: isDelivery ? 'delivery' as const : 'runtime' as const, actor: event.actor, note: String(event.payload.reason ?? event.payload.note ?? event.eventType), createdAt: event.createdAt, provenance: event.provenance }]
  })
}

export async function fetchWorkspaceSnapshot(filmId: string, revisionId: string): Promise<WorkspaceSnapshot> {
  const payload = await backendFetch<BackendWorkspacePayload>(`/workspace?filmId=${encodeURIComponent(filmId)}&revisionId=${encodeURIComponent(revisionId)}`)
  return normalizeWorkspacePayload(payload)
}

export async function tryBackendWorkspace(filmId: string, revisionId: string): Promise<WorkspaceSnapshot | null> {
  try {
    const snapshot = await fetchWorkspaceSnapshot(filmId, revisionId)
    setWorkspaceSnapshot(snapshot)
    return snapshot
  } catch {
    return null
  }
}

export function stageFromNodeLabel(label: string): PipelineStage | undefined {
  const normalized = label.toLowerCase()
  return ['script', 'scene', 'story beat', 'shoot', 'shot', 'take', 'edit', 'master', 'localization', 'delivery'].find((stage) => stage === normalized) as PipelineStage | undefined
}

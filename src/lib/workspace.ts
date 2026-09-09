import {
  type AgentEvent,
  type AgentEventPhase,
  type ApprovalDecision,
  type ApprovalRecord,
  type DeliveryApprovalRequest,
  type DeliveryConflictResolutionRequest,
  type DeliveryCompileRequest,
  type EditorialDecisionRequest,
  type GraphNodeData,
  type GraphNodeDraft,
  type Provenance,
  type ScriptGitDocument,
  type ScriptGitState,
  type Tone,
  type WorkflowEvent,
  type WorkspaceEdge,
  type WorkspaceNode,
  type WorkspaceSnapshot,
} from './contracts'

export * from './contracts'

export const WORKSPACE_ID = 'clio-local-demo'
export const FILM_ID = 'demo-feature'
export const REVISION_ID = 'rev-05'

const FRAME_RATE = 24

const now = () => new Date().toISOString()

const source = (
  value: Provenance['source'],
  label: string,
  detail?: string,
): Provenance => ({ source: value, label, ...(detail ? { detail } : {}) })

const computed = source('computed', 'COMPUTED')
const simulation = source('agent_simulation', 'LOCAL SIMULATION')

/** Format a duration as a compact editorial clock. */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remainder = total % 60
  if (hours > 0) return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

type BeatSeed = {
  number: number
  title: string
  text: string
  narration: string
  start: number
  end: number
}

type SceneSeed = {
  number: string
  heading: string
  text: string
  narration: string
  start: number
  end: number
  status: Tone
  beats: BeatSeed[]
}

/**
 * The local dataset is intentionally script-sized. A scene is the parent
 * graph node and every scene carries both screenplay action and a narration
 * track. Longer scenes are decomposed into timed child beats; those children
 * can be expanded in the map without turning the overview into a dashboard.
 */
const sceneSeeds: SceneSeed[] = [
  {
    number: '42',
    heading: 'INT. KITCHEN — NIGHT',
    text: 'Mara hides the brass key beneath a tea tin and checks the dark window.',
    narration: 'NARRATOR: The key is hidden, but the night is listening.',
    start: 0,
    end: 78,
    status: 'understood',
    beats: [
      { number: 1, title: 'SEARCH', text: 'Mara enters and checks the latch.', narration: 'NARRATOR: Every lock sounds louder after midnight.', start: 0, end: 34 },
      { number: 2, title: 'HIDE', text: 'She slips the brass key beneath a tea tin.', narration: 'MARA (V.O.): Keep it close. Keep it quiet.', start: 34, end: 78 },
    ],
  },
  {
    number: '43',
    heading: 'EXT. ALLEY — NIGHT',
    text: 'A phone vibrates. Mara follows the blue light into the rain.',
    narration: 'NARRATOR: A blue pulse draws her toward the unanswered call.',
    start: 78,
    end: 156,
    status: 'understood',
    beats: [
      { number: 1, title: 'FOLLOW', text: 'The phone vibrates in the puddle; Mara follows.', narration: 'NARRATOR: The signal moves before she does.', start: 78, end: 156 },
    ],
  },
  {
    number: '44',
    heading: 'INT. DINER — NIGHT',
    text: 'Jon slides a photograph across the table: the key belongs to his sister.',
    narration: 'JON: Your sister left this for you.',
    start: 156,
    end: 270,
    status: 'understood',
    beats: [
      { number: 1, title: 'ARRIVAL', text: 'Jon waits in the last booth, photograph face down.', narration: 'NARRATOR: The diner keeps one table for secrets.', start: 156, end: 190 },
      { number: 2, title: 'REVEAL', text: 'He turns the photograph toward Mara.', narration: 'JON: Look at the corner. That is her hand.', start: 190, end: 230 },
      { number: 3, title: 'CLAIM', text: 'The key is named as his sister’s message.', narration: 'MARA: Then why bring it to me?', start: 230, end: 270 },
    ],
  },
  {
    number: '45',
    heading: 'EXT. STREET — NIGHT',
    text: 'They leave before the bell rings. A pair of headlights turns the corner.',
    narration: 'NARRATOR: The bell never rings; the headlights do.',
    start: 270,
    end: 348,
    status: 'understood',
    beats: [
      { number: 1, title: 'EXIT', text: 'They leave the diner as headlights turn toward them.', narration: 'NARRATOR: Someone else has been waiting.', start: 270, end: 348 },
    ],
  },
  {
    number: '46',
    heading: 'INT. RESTAURANT — NIGHT',
    text: 'Mara stops Jon at the service door and demands the truth about the photograph.',
    narration: 'MARA: Tell me what the photograph proves.',
    start: 348,
    end: 456,
    status: 'understood',
    beats: [
      { number: 1, title: 'BLOCK', text: 'Mara catches Jon at the service door.', narration: 'NARRATOR: There is no quiet way out now.', start: 348, end: 400 },
      { number: 2, title: 'DEMAND', text: 'She demands the truth about the photograph.', narration: 'MARA: Say it before we move.', start: 400, end: 456 },
    ],
  },
  {
    number: '47',
    heading: 'MOVING CAR — NIGHT',
    text: 'Mara and Jon argue as city lights cut across the windshield; the key changes hands.',
    narration: 'NARRATOR: In motion, the truth has nowhere to sit.',
    start: 456,
    end: 588,
    status: 'breaking',
    beats: [
      { number: 1, title: 'PULL AWAY', text: 'Jon pulls into traffic before Mara can leave.', narration: 'NARRATOR: The road takes the choice from them.', start: 456, end: 488 },
      { number: 2, title: 'ARGUE', text: 'City lights strobe across the windshield as they argue.', narration: 'MARA: You changed the scene, not the truth.', start: 488, end: 524 },
      { number: 3, title: 'HANDOFF', text: 'Jon places the brass key in Mara’s palm.', narration: 'JON: Then carry it yourself.', start: 524, end: 560 },
      { number: 4, title: 'DECIDE', text: 'Mara closes her hand while the car keeps moving.', narration: 'NARRATOR: The handoff is small; the consequence is not.', start: 560, end: 588 },
    ],
  },
  {
    number: '48',
    heading: 'EXT. BRIDGE — DAWN',
    text: 'The car stops. Jon opens the key and reveals a tiny strip of film inside.',
    narration: 'JON: It was film all along.',
    start: 588,
    end: 690,
    status: 'pending',
    beats: [
      { number: 1, title: 'STOP', text: 'The car stops at the bridge as dawn arrives.', narration: 'NARRATOR: Stillness makes the secret visible.', start: 588, end: 638 },
      { number: 2, title: 'OPEN', text: 'Jon opens the key and reveals a strip of film.', narration: 'JON: This is what she wanted found.', start: 638, end: 690 },
    ],
  },
  {
    number: '49',
    heading: 'EXT. ROOFTOP — DAWN',
    text: 'Mara watches the city wake, finally choosing what to do with the evidence.',
    narration: 'NARRATOR: Dawn gives Mara one last clean choice.',
    start: 690,
    end: 780,
    status: 'pending',
    beats: [
      { number: 1, title: 'CHOICE', text: 'Mara watches the city wake and chooses the evidence.', narration: 'MARA (V.O.): I know where this belongs.', start: 690, end: 780 },
    ],
  },
]

const revisionBefore = 'Mara and Jon argue inside the restaurant; the key changes hands.'
const revisionAfter = 'Mara and Jon argue in a moving car; the key changes hands.'

const stageId = (number: string) => `scene-${number}`
const beatId = (sceneNumber: string, number: number) => `beat-${sceneNumber}-${String(number).padStart(2, '0')}`

const scenePosition = (index: number) => {
  const column = index % 4
  const row = Math.floor(index / 4)
  return { x: 250 + column * 285, y: 120 + row * 245 }
}

const revisionNode: WorkspaceNode = {
  id: 'revision-v5',
  position: { x: 24, y: 285 },
  data: {
    kind: 'revision',
    stage: 'Script',
    eyebrow: 'REVISION / SOURCE',
    title: 'V5 · SC 47',
    code: 'REV-05',
    metric: '1 CHANGE',
    secondary: 'SCRIPT',
    status: 'breaking',
    detail: 'The current revision changes the scene setting while preserving the handoff beat.',
    scriptText: revisionAfter,
    previousScriptText: revisionBefore,
    currentScriptText: revisionAfter,
    provenance: computed,
    entityType: 'revision',
    scope: 'revision',
  },
}

const sceneNodes: WorkspaceNode[] = sceneSeeds.map((scene, index) => {
  const duration = scene.end - scene.start
  const data: GraphNodeData = {
    kind: 'scene',
    stage: 'Script',
    stageIndex: 0,
    sceneNumber: scene.number,
    eyebrow: `SC ${scene.number}`,
    title: scene.heading,
    code: `${formatClock(scene.start)} → ${formatClock(scene.end)}`,
    metric: formatClock(duration),
    secondary: scene.number === '47' ? `CHANGED · B${String(scene.beats.length).padStart(2, '0')}` : `B${String(scene.beats.length).padStart(2, '0')}`,
    status: scene.status,
    detail: scene.text,
    scriptText: scene.text,
    narrationText: scene.narration,
    childCount: scene.beats.length,
    startSeconds: scene.start,
    endSeconds: scene.end,
    durationSeconds: duration,
    provenance: computed,
    entityType: 'scene',
    scope: scene.number === '47' ? 'focus' : 'film',
  }
  return { id: stageId(scene.number), position: scenePosition(index), data }
})

const beatNodes: WorkspaceNode[] = sceneSeeds.flatMap((scene, sceneIndex) => scene.beats.map((beat) => {
  const duration = beat.end - beat.start
  const parent = sceneNodes[sceneIndex]!
  const data: GraphNodeData = {
    kind: 'beat',
    stage: 'Script',
    stageIndex: 0,
    sceneNumber: scene.number,
    beatNumber: beat.number,
    parentSceneId: parent.id,
    eyebrow: `SC ${scene.number} / B${String(beat.number).padStart(2, '0')}`,
    title: beat.title,
    code: `${formatClock(beat.start)} → ${formatClock(beat.end)}`,
    metric: formatClock(duration),
    secondary: 'BEAT',
    status: scene.status,
    detail: beat.text,
    scriptText: beat.text,
    narrationText: beat.narration,
    startSeconds: beat.start,
    endSeconds: beat.end,
    durationSeconds: duration,
    provenance: computed,
    entityType: 'beat',
    scope: 'beat',
  }
  return {
    id: beatId(scene.number, beat.number),
    position: { x: parent.position.x + (beat.number - 1) * 195, y: parent.position.y + 132 },
    data,
  }
}))

const allNodes: WorkspaceNode[] = [revisionNode, ...sceneNodes, ...beatNodes]

const edge = (
  id: string,
  sourceId: string,
  targetId: string,
  relation: string,
  tone: Tone = 'understood',
  kind: WorkspaceEdge['data']['kind'] = 'backbone',
): WorkspaceEdge => ({
  id,
  source: sourceId,
  target: targetId,
  data: { relation, tone, branch: kind === 'beat' ? 'backbone' : kind, kind, provenance: computed },
})

const scriptEdges: WorkspaceEdge[] = [
  edge('e-revision-sc47', revisionNode.id, stageId('47'), 'revises', 'breaking'),
  ...sceneSeeds.slice(0, -1).map((scene, index) => edge(
    `e-scene-${scene.number}-${sceneSeeds[index + 1]!.number}`,
    stageId(scene.number),
    stageId(sceneSeeds[index + 1]!.number),
    'follows',
    scene.status,
  )),
  edge('e-sc42-setup-sc47', stageId('42'), stageId('47'), 'sets_up', 'understood'),
  edge('e-sc47-payoff-sc48', stageId('47'), stageId('48'), 'pays_off', 'breaking'),
  edge('e-sc44-context-sc47', stageId('44'), stageId('47'), 'motivates', 'understood'),
  ...sceneSeeds.flatMap((scene) => scene.beats.flatMap((beat, index) => {
    const current = beatId(scene.number, beat.number)
    const parent = stageId(scene.number)
    const contains = edge(`e-${parent}-${current}`, parent, current, 'contains', scene.status, 'beat')
    const follows = index > 0
      ? [edge(`e-${beatId(scene.number, scene.beats[index - 1]!.number)}-${current}`, beatId(scene.number, scene.beats[index - 1]!.number), current, 'follows', scene.status, 'beat')]
      : []
    return [contains, ...follows]
  })),
]

const totalDurationSeconds = sceneSeeds.reduce((latest, scene) => Math.max(latest, scene.end), 0)
const totalBeatCount = sceneSeeds.reduce((total, scene) => total + scene.beats.length, 0)

export const runtimeValue = (seconds: number) => ({
  value: Math.round(seconds / 60),
  provenance: computed,
})

const baseSnapshot: () => WorkspaceSnapshot = () => ({
  workspaceId: WORKSPACE_ID,
  filmId: FILM_ID,
  revisionId: REVISION_ID,
  revisionLabel: 'V5 · SC 47',
  title: 'CLIO',
  subtitle: 'CONTINUITY & LINEAGE INTELLIGENCE OPERATOR',
  changedScene: 'SC 47 · RESTAURANT → MOVING CAR',
  revisionBefore,
  revisionAfter,
  totalDurationSeconds,
  sceneCount: sceneSeeds.length,
  beatCount: totalBeatCount,
  frameRate: FRAME_RATE,
  currentRuntime: runtimeValue(totalDurationSeconds),
  targetRuntime: runtimeValue(totalDurationSeconds),
  deliveryCount: 0,
  graph: { nodes: structuredClone(allNodes), edges: structuredClone(scriptEdges) },
  runtimeProposals: [],
  deliveryVariants: [],
  approvals: [],
  workflowEvents: [],
  agentEvents: [],
  dataSource: source('computed', 'LOCAL FALLBACK', 'MCP-first; direct ClickHouse fallback when configured'),
  selectedNodeId: stageId('47'),
})

let serverSnapshot = baseSnapshot()

export function createFallbackSnapshot(): WorkspaceSnapshot {
  return structuredClone(baseSnapshot())
}

export function readWorkspaceSnapshot(): WorkspaceSnapshot {
  return structuredClone(serverSnapshot)
}

export function setWorkspaceSnapshot(snapshot: WorkspaceSnapshot): WorkspaceSnapshot {
  serverSnapshot = structuredClone(snapshot)
  return readWorkspaceSnapshot()
}

/** Apply a loaded GitHub document to the browser mirror when FastAPI is down. */
export function applyLocalScriptGit(snapshot: WorkspaceSnapshot, document: ScriptGitDocument): WorkspaceSnapshot {
  const next = structuredClone(snapshot)
  const state: ScriptGitState = {
    source: 'github', repository: document.repository, owner: document.owner, repo: document.repo,
    path: document.path, ref: document.ref, sha: document.sha, shortSha: document.shortSha,
    ...(document.htmlUrl ? { htmlUrl: document.htmlUrl } : {}), ...(document.rawUrl ? { rawUrl: document.rawUrl } : {}),
    ...(document.size !== undefined ? { size: document.size } : {}), ...(document.message ? { message: document.message } : {}),
    parsed: structuredClone(document.parsed), revisions: structuredClone(document.revisions), provenance: structuredClone(document.provenance),
  }
  next.scriptGit = state
  next.graph = { nodes: structuredClone(document.nodes), edges: structuredClone(document.edges) }
  next.revisionId = document.revisionId
  next.revisionLabel = `${document.shortSha} · GITHUB`
  next.changedScene = `${document.repository} · ${document.path}`
  next.revisionBefore = 'Previous GitHub commit'
  next.revisionAfter = document.message ?? `Loaded ${document.path}`
  next.sceneCount = document.parsed.sceneCount
  next.beatCount = document.parsed.beatCount
  next.totalDurationSeconds = document.parsed.durationSeconds
  next.currentRuntime = runtimeValue(document.parsed.durationSeconds)
  next.targetRuntime = runtimeValue(document.parsed.durationSeconds)
  next.deliveryCount = 0
  next.runtimeProposals = []
  next.deliveryVariants = []
  next.approvals = []
  const revision = next.graph.nodes.find((node) => node.data.kind === 'revision')
  next.selectedNodeId = revision?.id ?? next.graph.nodes.find((node) => node.data.kind === 'scene')?.id ?? ''
  appendWorkflowEvent(next, 'script.git.applied', 'EDITORIAL', {
    repository: document.repository,
    path: document.path,
    ref: document.ref,
    sha: document.sha,
    source: 'github',
    sceneCount: document.parsed.sceneCount,
    beatCount: document.parsed.beatCount,
  }, document.provenance)
  return next
}

function localMutationId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function assertDraftTiming(draft: GraphNodeDraft) {
  if (!Number.isFinite(draft.startSeconds) || !Number.isFinite(draft.endSeconds) || draft.startSeconds < 0 || draft.endSeconds <= draft.startSeconds) {
    throw new Error('End time must be greater than start time.')
  }
}

function refreshScriptTotals(snapshot: WorkspaceSnapshot) {
  const scenes = snapshot.graph.nodes.filter((node) => node.data.kind === 'scene')
  const beats = snapshot.graph.nodes.filter((node) => node.data.kind === 'beat')
  const total = scenes.reduce((max, node) => Math.max(max, node.data.endSeconds ?? 0), 0)
  snapshot.sceneCount = scenes.length
  snapshot.beatCount = beats.length
  snapshot.totalDurationSeconds = total
  snapshot.currentRuntime = runtimeValue(total)
  snapshot.targetRuntime = runtimeValue(total)
}

function localNodeProvenance(operation: string): Provenance {
  return { ...computed, label: 'LOCAL EDIT', detail: operation }
}

/** Apply a human-created scene or beat to the local mirror when the API is unavailable. */
export function createLocalGraphNode(snapshot: WorkspaceSnapshot, draft: GraphNodeDraft): WorkspaceSnapshot {
  assertDraftTiming(draft)
  const next = structuredClone(snapshot)
  const existing = next.graph.nodes
  const scenes = existing.filter((node) => node.data.kind === 'scene')
  const sequence = Math.max(0, ...existing.map((node) => node.data.stageIndex ?? 0), existing.length) + 1
  const heading = draft.heading.trim()
  const scriptText = draft.scriptText.trim()
  if (!heading || !scriptText) throw new Error('Heading and script text are required.')

  if (draft.kind === 'scene') {
    const sceneNumber = draft.sceneNumber?.trim() || String(Math.max(41, ...scenes.map((node) => Number(node.data.sceneNumber) || 0)) + 1)
    if (scenes.some((node) => node.data.sceneNumber === sceneNumber)) throw new Error(`SC ${sceneNumber} already exists.`)
    const node: WorkspaceNode = {
      id: localMutationId(`scene-${sceneNumber}`),
      position: scenePosition(scenes.length),
      data: {
        kind: 'scene', stage: 'Script', stageIndex: sequence, sceneNumber, eyebrow: `SC ${sceneNumber}`,
        title: heading, code: `${formatClock(draft.startSeconds)} → ${formatClock(draft.endSeconds)}`,
        metric: formatClock(draft.endSeconds - draft.startSeconds), secondary: 'B00', status: 'pending',
        detail: scriptText, scriptText, narrationText: draft.narrationText.trim() || undefined,
        childCount: 0, startSeconds: draft.startSeconds, endSeconds: draft.endSeconds,
        durationSeconds: draft.endSeconds - draft.startSeconds, provenance: localNodeProvenance('scene created'),
        entityType: 'scene', scope: 'film',
      },
    }
    const previous = scenes[scenes.length - 1]
    next.graph.nodes.push(node)
    if (previous) {
      next.graph.edges.push(edge(localMutationId('edge'), previous.id, node.id, 'follows', 'pending'))
    }
    appendWorkflowEvent(next, 'graph.node.created', 'EDITORIAL', { nodeId: node.id, kind: 'scene', sceneNumber }, node.data.provenance ?? computed)
    next.selectedNodeId = node.id
    refreshScriptTotals(next)
    return next
  }

  const parent = existing.find((node) => node.id === draft.parentSceneId && node.data.kind === 'scene')
  if (!parent) throw new Error('Choose a parent scene for this beat.')
  if (draft.startSeconds < (parent.data.startSeconds ?? 0) || draft.endSeconds > (parent.data.endSeconds ?? draft.endSeconds)) {
    throw new Error('Beat timing must fit inside its parent scene.')
  }
  const siblings = existing.filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === parent.id)
  const beatNumber = draft.beatNumber || Math.max(0, ...siblings.map((node) => node.data.beatNumber ?? 0)) + 1
  if (siblings.some((node) => node.data.beatNumber === beatNumber)) throw new Error(`B${String(beatNumber).padStart(2, '0')} already exists in this scene.`)
  const node: WorkspaceNode = {
    id: localMutationId(`beat-${parent.data.sceneNumber}-${beatNumber}`),
    position: { x: parent.position.x + (beatNumber - 1) * 195, y: parent.position.y + 132 },
    data: {
      kind: 'beat', stage: 'Script', stageIndex: sequence, sceneNumber: parent.data.sceneNumber, beatNumber,
      parentSceneId: parent.id, eyebrow: `SC ${parent.data.sceneNumber} / B${String(beatNumber).padStart(2, '0')}`,
      title: heading, code: `${formatClock(draft.startSeconds)} → ${formatClock(draft.endSeconds)}`,
      metric: formatClock(draft.endSeconds - draft.startSeconds), secondary: 'BEAT', status: parent.data.status,
      detail: scriptText, scriptText, narrationText: draft.narrationText.trim() || undefined,
      startSeconds: draft.startSeconds, endSeconds: draft.endSeconds, durationSeconds: draft.endSeconds - draft.startSeconds,
      provenance: localNodeProvenance('beat created'), entityType: 'beat', scope: 'beat',
    },
  }
  next.graph.nodes.push(node)
  next.graph.edges.push(edge(localMutationId('edge'), parent.id, node.id, 'contains', parent.data.status, 'beat'))
  const previous = siblings.sort((a, b) => (a.data.beatNumber ?? 0) - (b.data.beatNumber ?? 0)).at(-1)
  if (previous) next.graph.edges.push(edge(localMutationId('edge'), previous.id, node.id, 'follows', parent.data.status, 'beat'))
  const parentIndex = next.graph.nodes.findIndex((item) => item.id === parent.id)
  if (parentIndex >= 0) {
    next.graph.nodes[parentIndex]!.data.childCount = siblings.length + 1
    next.graph.nodes[parentIndex]!.data.secondary = parent.data.sceneNumber === '47' ? `CHANGED · B${String(siblings.length + 1).padStart(2, '0')}` : `B${String(siblings.length + 1).padStart(2, '0')}`
  }
  appendWorkflowEvent(next, 'graph.node.created', 'EDITORIAL', { nodeId: node.id, kind: 'beat', parentSceneId: parent.id, beatNumber }, node.data.provenance ?? computed)
  next.selectedNodeId = node.id
  refreshScriptTotals(next)
  return next
}

/** Update editable script fields in the local mirror. */
export function updateLocalGraphNode(snapshot: WorkspaceSnapshot, nodeId: string, draft: GraphNodeDraft): WorkspaceSnapshot {
  assertDraftTiming(draft)
  const next = structuredClone(snapshot)
  const node = next.graph.nodes.find((item) => item.id === nodeId)
  if (!node || !['scene', 'beat'].includes(node.data.kind)) throw new Error('Only scene and beat nodes can be edited.')
  const heading = draft.heading.trim()
  const scriptText = draft.scriptText.trim()
  if (!heading || !scriptText) throw new Error('Heading and script text are required.')
  if (node.data.kind === 'beat') {
    const parent = next.graph.nodes.find((item) => item.id === node.data.parentSceneId)
    if (parent && (draft.startSeconds < (parent.data.startSeconds ?? 0) || draft.endSeconds > (parent.data.endSeconds ?? draft.endSeconds))) {
      throw new Error('Beat timing must fit inside its parent scene.')
    }
  } else {
    const children = next.graph.nodes.filter((item) => item.data.kind === 'beat' && item.data.parentSceneId === node.id)
    if (children.some((child) => (child.data.startSeconds ?? 0) < draft.startSeconds || (child.data.endSeconds ?? 0) > draft.endSeconds)) {
      throw new Error('Scene timing must contain all child beats.')
    }
  }
  node.data.title = heading
  node.data.eyebrow = node.data.kind === 'beat' ? `SC ${node.data.sceneNumber} / B${String(node.data.beatNumber ?? 0).padStart(2, '0')}` : `SC ${node.data.sceneNumber}`
  node.data.code = `${formatClock(draft.startSeconds)} → ${formatClock(draft.endSeconds)}`
  node.data.metric = formatClock(draft.endSeconds - draft.startSeconds)
  node.data.detail = scriptText
  node.data.scriptText = scriptText
  node.data.narrationText = draft.narrationText.trim() || undefined
  node.data.startSeconds = draft.startSeconds
  node.data.endSeconds = draft.endSeconds
  node.data.durationSeconds = draft.endSeconds - draft.startSeconds
  node.data.provenance = localNodeProvenance('node updated')
  appendWorkflowEvent(next, 'graph.node.updated', 'EDITORIAL', { nodeId, kind: node.data.kind }, node.data.provenance)
  refreshScriptTotals(next)
  return next
}

/** Delete a scene/beat from the local mirror, cascading scene children. */
export function deleteLocalGraphNode(snapshot: WorkspaceSnapshot, nodeId: string): WorkspaceSnapshot {
  const next = structuredClone(snapshot)
  const target = next.graph.nodes.find((node) => node.id === nodeId)
  if (!target || !['scene', 'beat'].includes(target.data.kind)) throw new Error('Only scene and beat nodes can be deleted.')
  const deleted = new Set([nodeId])
  if (target.data.kind === 'scene') {
    for (const node of next.graph.nodes) if (node.data.kind === 'beat' && node.data.parentSceneId === nodeId) deleted.add(node.id)
  }
  next.graph.nodes = next.graph.nodes.filter((node) => !deleted.has(node.id))
  next.graph.edges = next.graph.edges.filter((item) => !deleted.has(item.source) && !deleted.has(item.target))
  const parent = target.data.kind === 'beat' ? next.graph.nodes.find((node) => node.id === target.data.parentSceneId) : undefined
  if (parent) {
    const count = next.graph.nodes.filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === parent.id).length
    parent.data.childCount = count
    parent.data.secondary = parent.data.sceneNumber === '47' && parent.data.status === 'breaking' ? `CHANGED · B${String(count).padStart(2, '0')}` : `B${String(count).padStart(2, '0')}`
  }
  appendWorkflowEvent(next, 'graph.node.deleted', 'EDITORIAL', { nodeId, deletedIds: [...deleted].join(',') }, localNodeProvenance('node deleted'))
  const replacement = next.graph.nodes.find((node) => node.data.kind === 'scene') ?? next.graph.nodes.find((node) => node.data.kind === 'revision')
  next.selectedNodeId = replacement?.id ?? ''
  refreshScriptTotals(next)
  return next
}

/** Kept as a compatibility helper for older server-function callers. */
export function stageIds() {
  return sceneSeeds.map((scene) => stageId(scene.number))
}

function appendWorkflowEvent(
  snapshot: WorkspaceSnapshot,
  eventType: string,
  actor: string,
  payload: Record<string, string | number | boolean | null>,
  provenance: Provenance,
) {
  const event: WorkflowEvent = {
    eventType,
    workflowId: snapshot.workspaceId,
    actor,
    payload,
    provenance,
    createdAt: now(),
  }
  snapshot.workflowEvents = [...snapshot.workflowEvents, event]
}

/** Generic human decision mirror retained for the existing boundary API. */
export function applyApproval(
  snapshot: WorkspaceSnapshot,
  input: { nodeId: string; decision: ApprovalDecision; reviewer?: string; note?: string },
) {
  const next = structuredClone(snapshot)
  const approval: ApprovalRecord = {
    id: `approval-${next.approvals.length + 1}`,
    decision: input.decision,
    target: 'runtime',
    actor: input.reviewer ?? 'EDITORIAL',
    note: input.note ?? (input.decision === 'approve' ? 'Approved in CLIO.' : 'Held for review.'),
    createdAt: now(),
    provenance: { ...computed, label: 'HUMAN DECISION' },
  }
  next.approvals = [...next.approvals, approval]
  const node = next.graph.nodes.find((item) => item.id === input.nodeId)
  if (node && input.decision === 'approve') {
    node.data.status = 'resolved'
    node.data.selectedAction = true
  }
  appendWorkflowEvent(next, input.decision === 'approve' ? 'script.node.approved' : 'script.node.held', approval.actor, { nodeId: input.nodeId }, approval.provenance)
  next.selectedNodeId = input.nodeId
  return next
}

export function recordApproval(input: { nodeId: string; decision: ApprovalDecision; reviewer?: string; note?: string }) {
  return setWorkspaceSnapshot(applyApproval(serverSnapshot, input))
}

/** Compatibility no-op: runtime proposals are intentionally out of this slice. */
export function selectProposal(snapshot: WorkspaceSnapshot, proposalId: string): WorkspaceSnapshot {
  const next = structuredClone(snapshot)
  appendWorkflowEvent(next, 'script.proposal.selected', 'EDITORIAL', { proposalId }, computed)
  return next
}

/** Compatibility no-op: delivery compilation is intentionally out of this slice. */
export function compileDelivery(snapshot: WorkspaceSnapshot, _request?: DeliveryCompileRequest): WorkspaceSnapshot {
  return structuredClone(snapshot)
}

export function approveDeliveryVariant(snapshot: WorkspaceSnapshot, _request: DeliveryApprovalRequest): WorkspaceSnapshot {
  return structuredClone(snapshot)
}

export function resolveDeliveryConflict(snapshot: WorkspaceSnapshot, _request: DeliveryConflictResolutionRequest): WorkspaceSnapshot {
  return structuredClone(snapshot)
}

export function applyEditorialDecision(snapshot: WorkspaceSnapshot, request: EditorialDecisionRequest): WorkspaceSnapshot {
  return applyApproval(snapshot, {
    nodeId: request.proposalId,
    decision: request.decision,
    reviewer: request.actor,
    ...(request.note ? { note: request.note } : {}),
  })
}

export function lineageFor(snapshot: WorkspaceSnapshot, nodeId: string): string[] {
  const upstream = new Map<string, string[]>()
  for (const item of snapshot.graph.edges) {
    upstream.set(item.target, [...(upstream.get(item.target) ?? []), item.source])
  }
  const seen = new Set<string>()
  const visit = (id: string) => {
    if (seen.has(id)) return
    seen.add(id)
    for (const parent of upstream.get(id) ?? []) visit(parent)
  }
  visit(nodeId)
  return [...seen]
}

export function downstreamFor(snapshot: WorkspaceSnapshot, nodeId: string): string[] {
  const downstream = new Map<string, string[]>()
  for (const item of snapshot.graph.edges) {
    downstream.set(item.source, [...(downstream.get(item.source) ?? []), item.target])
  }
  const seen = new Set<string>()
  const visit = (id: string) => {
    if (seen.has(id)) return
    seen.add(id)
    for (const child of downstream.get(id) ?? []) visit(child)
  }
  visit(nodeId)
  return [...seen]
}

type LocalAgentContext = {
  action?: 'inspect' | 'edit' | 'remove' | 'add'
  focusNode?: string
  prompt?: string
}

function focusScene(snapshot: WorkspaceSnapshot, requested: string | undefined): WorkspaceNode {
  const wanted = requested?.replace(/^\[FOCUS:/i, '').replace(/\]$/, '')
  return snapshot.graph.nodes.find((node) => node.id === wanted)
    ?? snapshot.graph.nodes.find((node) => node.data.sceneNumber === wanted)
    ?? snapshot.graph.nodes.find((node) => node.data.title.toLowerCase() === wanted?.toLowerCase())
    ?? snapshot.graph.nodes.find((node) => node.id === snapshot.selectedNodeId)
    ?? snapshot.graph.nodes[1]!
}

function sceneLabel(node: WorkspaceNode | undefined): string {
  if (!node) return 'NONE'
  if (node.data.sceneNumber && node.data.beatNumber) return `SC ${node.data.sceneNumber} / B${String(node.data.beatNumber).padStart(2, '0')}`
  return node.data.sceneNumber ? `SC ${node.data.sceneNumber}` : node.data.title
}

function actionFromPrompt(prompt: string | undefined): 'inspect' | 'edit' | 'remove' | 'add' {
  const value = (prompt ?? '').toLowerCase()
  if (/\b(remove|delete)\b/.test(value)) return 'remove'
  if (/\b(add|insert)\b/.test(value)) return 'add'
  if (/\b(edit|change)\b/.test(value)) return 'edit'
  return 'inspect'
}

/** Build a compact local stream from the same graph the UI is displaying. */
export function createAgentEventStream(snapshot: WorkspaceSnapshot, context: LocalAgentContext = {}): AgentEvent[] {
  const focus = focusScene(snapshot, context.focusNode)
  const action = context.action ?? actionFromPrompt(context.prompt)
  const upstreamIds = lineageFor(snapshot, focus.id).filter((id) => id !== focus.id)
  const downstreamIds = downstreamFor(snapshot, focus.id).filter((id) => id !== focus.id)
  const labelsFor = (ids: string[]) => [...new Set(ids
    .map((id) => snapshot.graph.nodes.find((node) => node.id === id))
    .filter((node): node is WorkspaceNode => node !== undefined && (node.data.kind !== 'beat' || focus.data.kind === 'beat'))
    .map(sceneLabel))].slice(0, 8).join(' · ')
  const upstream = labelsFor(upstreamIds) || 'NONE'
  const downstream = labelsFor(downstreamIds) || 'NONE'
  const duration = focus.data.durationSeconds ?? 0
  const afterRemove = Math.max(0, snapshot.totalDurationSeconds - duration)
  const childBeats = snapshot.graph.nodes
    .filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === focus.id)
    .sort((a, b) => (a.data.beatNumber ?? 0) - (b.data.beatNumber ?? 0))
  const beatSummary = childBeats.map(sceneLabel).join(' · ') || 'NONE'
  const affectedSceneLabels = [...new Set(downstreamIds
    .map((id) => snapshot.graph.nodes.find((node) => node.id === id))
    .filter((node): node is WorkspaceNode => node !== undefined && node.data.kind !== 'beat')
    .map(sceneLabel))]
  const affectedBeatLabels = [...new Set(downstreamIds
    .map((id) => snapshot.graph.nodes.find((node) => node.id === id))
    .filter((node): node is WorkspaceNode => node !== undefined && node.data.kind === 'beat')
    .map(sceneLabel))]
  const affectedScenes = focus.data.kind === 'beat'
    ? `${focus.data.parentSceneId ? sceneLabel(snapshot.graph.nodes.find((node) => node.id === focus.data.parentSceneId)) : 'PARENT'} → BEATS ${affectedBeatLabels.join(' · ') || 'NO DEPENDENT BEATS'}`
    : affectedSceneLabels.join(' · ') || downstream
  const actionDetail = {
    inspect: `UPSTREAM: ${upstream} · DOWNSTREAM: ${downstream} · BEATS: ${beatSummary}`,
    edit: `AFFECTED: ${focus.data.kind === 'beat' ? 'BEAT PATH ' : 'SCENES '}${affectedScenes || 'NO DOWNSTREAM SCENES'} · BEATS: ${beatSummary}`,
    remove: `UNNEEDED IF REMOVED: ${affectedScenes || 'NO DEPENDENT SCENES'} · BEATS: ${beatSummary} · FILM ${formatClock(afterRemove)}`,
    add: `POSSIBLE CONNECTIONS: ${upstream || 'START'} → NEW → ${downstream || 'END'}`,
  }[action]
  const analytics = action === 'remove'
    ? `${sceneLabel(focus)} ${formatClock(duration)} removed · ${formatClock(snapshot.totalDurationSeconds)} → ${formatClock(afterRemove)}`
    : `FOCUS ${formatClock(duration)} · FILM TOTAL ${formatClock(snapshot.totalDurationSeconds)}`
  const at = now()
  const event = (phase: AgentEventPhase, label: string, detail: string, tone: Tone = 'understood'): AgentEvent => ({
    id: `agent-${action}-${focus.id}-${phase}`,
    phase,
    label,
    detail,
    tone,
    createdAt: at,
    provenance: simulation,
  })
  return [
    event('narrative', 'SCRIPT / READ', `${sceneLabel(focus)} · ${focus.data.scriptText ?? focus.data.detail ?? ''} · NARRATION: ${focus.data.narrationText ?? '—'}`),
    event('graph', 'GRAPH / TRACED', actionDetail, action === 'edit' || action === 'remove' ? 'breaking' : 'understood'),
    event('analytics', 'TIME / COMPUTED', analytics),
    event('revision', 'REVISION / V5', `${sceneLabel(focus)} is the ${focus.id === 'revision-v5' ? 'source change' : 'selected script node'}.`),
    event('critic', 'CRITIC / PROPOSE', action === 'inspect' ? 'No write proposed; review the path first.' : 'Proposal only; a person must decide whether to change the script.', 'pending'),
  ]
}

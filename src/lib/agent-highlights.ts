import type { WorkspaceNode, WorkspaceSnapshot } from './contracts'

/**
 * Evidence returned by an agent is deliberately treated as display data. It
 * can contain stable node ids from a tool result, screenplay labels such as
 * `SC 17 / B02`, or ordinary scene/beat names in a final recommendation.
 * This module resolves that evidence back to the current graph without
 * making another provider request.
 */

const ID_KEYS = new Set([
  'id',
  'node_id',
  'nodeId',
  'focus_node',
  'focusNode',
  'parent_scene_id',
  'parentSceneId',
])

const EVIDENCE_KEYS = new Set([
  'assessment',
  'change',
  'detail',
  'downstream',
  'focus',
  'lineage',
  'message',
  'notes',
  'recommendation',
  'result',
  'upstream',
  'payload',
  'arguments',
  'affected',
  'affected_nodes',
  'affectedNodes',
  'node_ids',
  'nodeIds',
  'nodes',
  'relations',
])

function normalize(value: string): string {
  return value
    .toLocaleLowerCase()
    .replace(/[—–−]/g, '-')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function tokenPattern(value: string): RegExp | undefined {
  const normalized = normalize(value)
  if (normalized.length < 3) return undefined
  const tokens = normalized.split(/\s+/).filter(Boolean)
  if (tokens.length === 0) return undefined
  return new RegExp(`(?:^|\\s)${tokens.map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\s+')}(?=$|\\s)`, 'i')
}

function nodeLabel(node: WorkspaceNode): string {
  if (node.data.sceneNumber && node.data.beatNumber !== undefined) {
    return `SC ${node.data.sceneNumber} / B${String(node.data.beatNumber).padStart(2, '0')}`
  }
  if (node.data.sceneNumber) return `SC ${node.data.sceneNumber}`
  return node.data.title
}

function isIdentityKey(key: string): boolean {
  return ID_KEYS.has(key)
}

function isEvidenceKey(key: string): boolean {
  return EVIDENCE_KEYS.has(key)
}

/**
 * Pull only agent evidence fields from a streamed payload. In particular,
 * this avoids treating a complete graph context as a recommendation that
 * mentions every node, while still accepting tool-result `nodes` arrays.
 */
function collectEvidence(value: unknown, key = ''): string[] {
  if (typeof value === 'string' || typeof value === 'number') return [String(value)]
  if (Array.isArray(value)) return value.flatMap((item) => collectEvidence(item, key))
  if (!value || typeof value !== 'object') return []

  const record = value as Record<string, unknown>
  const result: string[] = []
  for (const [childKey, childValue] of Object.entries(record)) {
    if (isIdentityKey(childKey)) {
      // An id-like value is useful even when it appears in a nested tool
      // result. Non-id metadata stays out of this branch.
      if (typeof childValue === 'string' || typeof childValue === 'number') result.push(String(childValue))
      else result.push(...collectEvidence(childValue, childKey))
      continue
    }
    if (childKey === 'nodes' && Array.isArray(childValue)) {
      for (const node of childValue) {
        if (!node || typeof node !== 'object') continue
        const item = node as Record<string, unknown>
        for (const identity of ['id', 'node_id', 'scene_number', 'beat_number', 'label', 'heading', 'title']) {
          const candidate = item[identity]
          if (typeof candidate === 'string' || typeof candidate === 'number') result.push(String(candidate))
        }
      }
      continue
    }
    if (isEvidenceKey(childKey) || isEvidenceKey(key)) result.push(...collectEvidence(childValue, childKey))
  }
  return result
}

function titleCandidates(node: WorkspaceNode): string[] {
  const values = [node.data.title, node.data.eyebrow, node.data.code, nodeLabel(node)]
  // Short action words (OPEN, STOP, HIDE, etc.) are too common in prose to
  // safely resolve to a beat. Scene headings and multi-word beat names remain
  // useful fallbacks when a live provider omits the SC/B identifier.
  return values.filter((value): value is string => Boolean(value && normalize(value).length >= 5 && (value.includes(' ') || value.length >= 5)))
}

function candidateMatches(text: string, candidate: string, node: WorkspaceNode): boolean {
  if (candidate === node.id && text.toLocaleLowerCase().includes(node.id.toLocaleLowerCase())) return true
  const pattern = tokenPattern(candidate)
  return Boolean(pattern?.test(normalize(text)))
}

/**
 * Return graph node ids mentioned by one or more agent result payloads.
 * Results preserve graph order so the UI is stable and deterministic.
 */
export function nodeIdsMentionedInAgentEvidence(snapshot: WorkspaceSnapshot, ...evidence: unknown[]): string[] {
  const text = evidence.flatMap((item) => collectEvidence(item)).join(' · ')
  if (!text) return []
  const matched = new Set<string>()
  for (const node of snapshot.graph.nodes) {
    const candidates = [node.id, nodeLabel(node), ...titleCandidates(node)]
    if (candidates.some((candidate) => candidateMatches(text, candidate, node))) matched.add(node.id)
  }
  return snapshot.graph.nodes.filter((node) => matched.has(node.id)).map((node) => node.id)
}

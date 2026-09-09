import { describe, expect, it } from 'vitest'
import {
  applyApproval,
  createAgentEventStream,
  createFallbackSnapshot,
  createLocalGraphNode,
  deleteLocalGraphNode,
  downstreamFor,
  formatClock,
  lineageFor,
  stageIds,
  updateLocalGraphNode,
} from './workspace'

describe('script workspace graph', () => {
  it('keeps every timed scene and the visible revision source', () => {
    const snapshot = createFallbackSnapshot()
    const scenes = snapshot.graph.nodes.filter((node) => node.data.kind === 'scene')

    expect(stageIds()).toHaveLength(8)
    expect(scenes).toHaveLength(8)
    expect(snapshot.beatCount).toBe(16)
    expect(snapshot.graph.nodes.filter((node) => node.data.kind === 'beat')).toHaveLength(16)
    expect(snapshot.graph.nodes.find((node) => node.id === 'revision-v5')?.data.kind).toBe('revision')
    expect(snapshot.graph.edges).toHaveLength(35)
    expect(snapshot.totalDurationSeconds).toBe(780)
    expect(formatClock(scenes[5]!.data.durationSeconds ?? 0)).toBe('02:12')
    expect(scenes[5]!.data.narrationText).toContain('truth has nowhere')
    const beats = snapshot.graph.nodes.filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === 'scene-47')
    expect(beats).toHaveLength(4)
    beats.forEach((beat) => {
      expect(beat.data.startSeconds! >= 456).toBe(true)
      expect(beat.data.endSeconds! <= 588).toBe(true)
      expect(beat.data.endSeconds! - beat.data.startSeconds!).toBe(beat.data.durationSeconds)
      expect(beat.data.narrationText).toBeTruthy()
    })
    scenes.forEach((scene, index) => {
      expect(scene.data.endSeconds! - scene.data.startSeconds!).toBe(scene.data.durationSeconds)
      if (index > 0) expect(scene.data.startSeconds).toBe(scenes[index - 1]!.data.endSeconds)
    })
  })

  it('maps lineage around SC 47 and records a human decision without changing text', () => {
    const snapshot = createFallbackSnapshot()
    const upstream = lineageFor(snapshot, 'scene-47')
    const downstream = downstreamFor(snapshot, 'scene-47')

    expect(upstream).toContain('revision-v5')
    expect(upstream).toContain('scene-42')
    expect(downstream).toContain('scene-48')
    expect(downstream).toContain('scene-49')

    const approved = applyApproval(snapshot, {
      nodeId: 'scene-47',
      decision: 'approve',
      reviewer: 'EDITORIAL',
      note: 'Keep the moving-car revision.',
    })
    expect(approved.approvals[0]?.decision).toBe('approve')
    expect(approved.graph.nodes.find((node) => node.id === 'scene-47')?.data.status).toBe('resolved')
    expect(approved.workflowEvents.at(-1)?.eventType).toBe('script.node.approved')
  })

  it('answers edit, remove, and add questions from the same graph', () => {
    const snapshot = createFallbackSnapshot()
    const edit = createAgentEventStream(snapshot, { action: 'edit', focusNode: 'scene-47' })
    const remove = createAgentEventStream(snapshot, { action: 'remove', focusNode: 'scene-47' })
    const add = createAgentEventStream(snapshot, { action: 'add', focusNode: 'scene-47' })

    expect(edit.find((event) => event.phase === 'graph')?.detail).toContain('AFFECTED')
    expect(remove.find((event) => event.phase === 'analytics')?.detail).toContain('10:48')
    expect(add.find((event) => event.phase === 'graph')?.detail).toContain('POSSIBLE CONNECTIONS')
    expect(edit.find((event) => event.phase === 'narrative')?.detail).toContain('NARRATION:')
    expect(new Set(edit.map((event) => event.provenance.source))).toEqual(new Set(['agent_simulation']))
  })

  it('supports scene and child-beat CRUD in the local mirror', () => {
    const initial = createFallbackSnapshot()
    const createdScene = createLocalGraphNode(initial, {
      kind: 'scene',
      sceneNumber: '50',
      heading: 'INT. TEST ROOM — NIGHT',
      scriptText: 'A new scene enters the cut.',
      narrationText: 'NARRATOR: A new line joins the map.',
      startSeconds: 780,
      endSeconds: 840,
    })
    const scene = createdScene.graph.nodes.find((node) => node.data.sceneNumber === '50' && node.data.kind === 'scene')!
    expect(createdScene.sceneCount).toBe(9)
    expect(scene.data.durationSeconds).toBe(60)
    expect(createdScene.workflowEvents.at(-1)?.eventType).toBe('graph.node.created')

    const withBeat = createLocalGraphNode(createdScene, {
      kind: 'beat',
      parentSceneId: scene.id,
      heading: 'TURN',
      scriptText: 'Mara turns toward the window.',
      narrationText: 'NARRATOR: The room gives way to motion.',
      startSeconds: 800,
      endSeconds: 840,
    })
    const beat = withBeat.graph.nodes.find((node) => node.data.kind === 'beat' && node.data.parentSceneId === scene.id)!
    expect(withBeat.beatCount).toBe(17)
    expect(withBeat.graph.edges.some((edge) => edge.source === scene.id && edge.target === beat.id && edge.data.relation === 'contains')).toBe(true)

    const edited = updateLocalGraphNode(withBeat, beat.id, {
      kind: 'beat',
      parentSceneId: scene.id,
      heading: 'TURN',
      scriptText: 'Mara turns toward the rear window.',
      narrationText: 'NARRATOR: The turn is now part of the record.',
      startSeconds: 810,
      endSeconds: 840,
    })
    expect(edited.graph.nodes.find((node) => node.id === beat.id)?.data.durationSeconds).toBe(30)

    const removed = deleteLocalGraphNode(edited, scene.id)
    expect(removed.sceneCount).toBe(8)
    expect(removed.beatCount).toBe(16)
    expect(removed.graph.nodes.some((node) => node.id === scene.id || node.id === beat.id)).toBe(false)
    expect(removed.workflowEvents.at(-1)?.eventType).toBe('graph.node.deleted')
  })
})

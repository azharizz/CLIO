import { describe, expect, it } from 'vitest'
import { buildFilmMap, overviewAnchorFor, traceAnchorFor } from './film-map'
import { createFallbackSnapshot } from './workspace'

describe('film map', () => {
  it('uses the same complete timed script graph for map and trace', () => {
    const snapshot = createFallbackSnapshot()
    const map = buildFilmMap(snapshot)

    expect(map.nodes).toHaveLength(9)
    expect(map.nodes.filter((node) => node.data.kind === 'scene')).toHaveLength(8)
    expect(snapshot.graph.nodes.filter((node) => node.data.kind === 'beat')).toHaveLength(16)
    expect(map.nodes.some((node) => node.data.kind === 'beat')).toBe(false)
    expect(map.nodes.some((node) => node.data.title.includes('MASTER'))).toBe(false)
    expect(map.nodes.some((node) => node.data.title.includes('LANGUAGE'))).toBe(false)
    expect(map.edges).toHaveLength(11)
  })

  it('reveals only the selected scene children when expanded', () => {
    const map = buildFilmMap(createFallbackSnapshot(), 'scene-47')
    expect(map.nodes.filter((node) => node.data.kind === 'beat')).toHaveLength(4)
    expect(map.nodes.filter((node) => node.data.kind === 'scene')).toHaveLength(8)
    expect(map.edges.filter((edge) => edge.data.kind === 'beat')).toHaveLength(7)
  })

  it('keeps expanded children local to each parent scene', () => {
    const snapshot = createFallbackSnapshot()
    const map = buildFilmMap(snapshot, new Set(['scene-42', 'scene-47']))

    expect(map.nodes.filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === 'scene-42')).toHaveLength(2)
    expect(map.nodes.filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === 'scene-47')).toHaveLength(4)
    expect(map.nodes.filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === 'scene-43')).toHaveLength(0)
    // Visibility is a projection only: the agent/calculation graph stays whole.
    expect(snapshot.graph.nodes.filter((node) => node.data.kind === 'beat')).toHaveLength(16)
  })

  it('keeps selection as the trace anchor', () => {
    expect(traceAnchorFor('scene-47')).toBe('scene-47')
    expect(overviewAnchorFor('scene-47')).toBe('scene-47')
  })
})

import { describe, expect, it } from 'vitest'
import { buildFilmMap, overviewAnchorFor, traceAnchorFor } from './film-map'
import { createFallbackSnapshot } from './workspace'

describe('film map', () => {
  it('uses the same complete timed script graph for map and trace', () => {
    const snapshot = createFallbackSnapshot()
    const map = buildFilmMap(snapshot)

    expect(map.nodes).toHaveLength(26)
    expect(map.nodes.filter((node) => node.data.kind === 'scene')).toHaveLength(25)
    expect(snapshot.graph.nodes.filter((node) => node.data.kind === 'beat')).toHaveLength(125)
    expect(map.nodes.some((node) => node.data.kind === 'beat')).toBe(false)
    expect(map.nodes.some((node) => node.data.title.includes('MASTER OUTPUT'))).toBe(false)
    expect(map.nodes.some((node) => node.data.title.includes('LANGUAGE SET'))).toBe(false)
    expect(map.edges).toHaveLength(28)
  })

  it('reveals only the selected scene children when expanded', () => {
    const map = buildFilmMap(createFallbackSnapshot(), 'scene-17')
    expect(map.nodes.filter((node) => node.data.kind === 'beat')).toHaveLength(5)
    expect(map.nodes.filter((node) => node.data.kind === 'scene')).toHaveLength(25)
    expect(map.edges.filter((edge) => edge.data.kind === 'beat')).toHaveLength(9)
  })

  it('keeps expanded children local to each parent scene', () => {
    const snapshot = createFallbackSnapshot()
    const map = buildFilmMap(snapshot, new Set(['scene-01', 'scene-17']))

    expect(map.nodes.filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === 'scene-01')).toHaveLength(5)
    expect(map.nodes.filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === 'scene-17')).toHaveLength(5)
    expect(map.nodes.filter((node) => node.data.kind === 'beat' && node.data.parentSceneId === 'scene-02')).toHaveLength(0)
    // Visibility is a projection only: the agent/calculation graph stays whole.
    expect(snapshot.graph.nodes.filter((node) => node.data.kind === 'beat')).toHaveLength(125)
  })

  it('keeps selection as the trace anchor', () => {
    expect(traceAnchorFor('scene-17')).toBe('scene-17')
    expect(overviewAnchorFor('scene-17')).toBe('scene-17')
  })
})

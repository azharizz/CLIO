import { describe, expect, it } from 'vitest'
import { createFallbackSnapshot } from './workspace'
import { nodeIdsMentionedInAgentEvidence } from './agent-highlights'

describe('agent related-node evidence', () => {
  it('resolves scene labels without confusing partial scene numbers', () => {
    const snapshot = createFallbackSnapshot()

    expect(nodeIdsMentionedInAgentEvidence(snapshot, 'AFFECTED: SC 18 · SC 19')).toEqual([
      'scene-18',
      'scene-19',
    ])
  })

  it('resolves a child beat and its parent from a specific SC/B label', () => {
    const snapshot = createFallbackSnapshot()

    const ids = nodeIdsMentionedInAgentEvidence(snapshot, 'The affected path is SC 17 / B02.')

    expect(ids).toContain('scene-17')
    expect(ids).toContain('beat-17-02')
    expect(ids).not.toContain('beat-17-01')
  })

  it('accepts stable ids and tool-result node arrays', () => {
    const snapshot = createFallbackSnapshot()

    const ids = nodeIdsMentionedInAgentEvidence(snapshot, {
      payload: {
        result: {
          nodes: [{ id: 'scene-18' }, { id: 'beat-17-03' }],
        },
      },
    })

    expect(ids).toEqual(['scene-18', 'beat-17-03'])
  })

  it('does not turn common short beat words into false positives', () => {
    const snapshot = createFallbackSnapshot()

    expect(nodeIdsMentionedInAgentEvidence(snapshot, 'The next action is to open the door and stop.')).toEqual([])
  })
})

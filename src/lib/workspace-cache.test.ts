import { beforeEach, describe, expect, it } from 'vitest'
import { createFallbackSnapshot } from './workspace'
import {
  WORKSPACE_CACHE_MAX_STALE_MS,
  WORKSPACE_CACHE_TTL_MS,
  invalidateWorkspaceCache,
  readWorkspaceCache,
  writeWorkspaceCache,
} from './workspace-cache'

describe('workspace stale-while-revalidate cache', () => {
  beforeEach(() => invalidateWorkspaceCache())

  it('stores authoritative ClickHouse snapshots and reports their age', () => {
    const snapshot = createFallbackSnapshot()
    snapshot.dataSource = { source: 'direct_clickhouse', label: 'DIRECT CLICKHOUSE' }
    const storedAt = 10_000

    expect(writeWorkspaceCache(snapshot, storedAt)).toBe(true)
    expect(readWorkspaceCache(snapshot.filmId, snapshot.revisionId, storedAt + 1_000)?.isFresh).toBe(true)
    expect(readWorkspaceCache(snapshot.filmId, snapshot.revisionId, storedAt + WORKSPACE_CACHE_TTL_MS + 1)?.isFresh).toBe(false)
    expect(readWorkspaceCache(snapshot.filmId, snapshot.revisionId, storedAt + WORKSPACE_CACHE_TTL_MS + 1)?.ageMs).toBe(WORKSPACE_CACHE_TTL_MS + 1)
  })

  it('drops entries after the maximum stale window and never caches local fallback data', () => {
    const fallback = createFallbackSnapshot()
    expect(writeWorkspaceCache(fallback)).toBe(false)
    expect(readWorkspaceCache(fallback.filmId, fallback.revisionId)).toBeNull()

    const remote = createFallbackSnapshot()
    remote.dataSource = { source: 'clickhouse_mcp', label: 'CLICKHOUSE MCP' }
    const storedAt = 20_000
    writeWorkspaceCache(remote, storedAt)
    expect(readWorkspaceCache(remote.filmId, remote.revisionId, storedAt + WORKSPACE_CACHE_MAX_STALE_MS + 1)).toBeNull()
  })

  it('invalidates entries explicitly after a write', () => {
    const snapshot = createFallbackSnapshot()
    snapshot.dataSource = { source: 'direct_clickhouse', label: 'DIRECT CLICKHOUSE' }
    writeWorkspaceCache(snapshot)
    invalidateWorkspaceCache(snapshot.filmId, snapshot.revisionId)
    expect(readWorkspaceCache(snapshot.filmId, snapshot.revisionId)).toBeNull()
  })
})


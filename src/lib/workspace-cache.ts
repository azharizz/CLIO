import type { WorkspaceSnapshot } from './contracts'

/**
 * A small stale-while-revalidate cache for the read-only workspace snapshot.
 *
 * The authoritative copy remains FastAPI/ClickHouse. This cache only makes
 * the shell useful while the remote snapshot is being refreshed; mutations
 * explicitly invalidate it from the workspace route.
 */
export const WORKSPACE_CACHE_TTL_MS = 30_000
export const WORKSPACE_CACHE_MAX_STALE_MS = 5 * 60_000

const CACHE_VERSION = 1
const STORAGE_PREFIX = 'clio-workspace-cache-v1'

interface WorkspaceCacheEnvelope {
  version: number
  key: string
  storedAt: number
  snapshot: WorkspaceSnapshot
}

export interface WorkspaceCacheEntry {
  snapshot: WorkspaceSnapshot
  ageMs: number
  isFresh: boolean
}

const memoryCache = new Map<string, WorkspaceCacheEnvelope>()

function cacheKey(filmId: string, revisionId: string): string {
  return `${filmId}::${revisionId}`
}

function storageKey(key: string): string {
  return `${STORAGE_PREFIX}:${encodeURIComponent(key)}`
}

function browserStorage(): Storage | undefined {
  if (typeof window === 'undefined') return undefined
  try {
    return window.sessionStorage
  } catch {
    return undefined
  }
}

function isCacheable(snapshot: WorkspaceSnapshot): boolean {
  return !snapshot.providerError
    && (snapshot.dataSource.source === 'direct_clickhouse' || snapshot.dataSource.source === 'clickhouse_mcp')
}

function cloneEnvelope(envelope: WorkspaceCacheEnvelope): WorkspaceCacheEnvelope {
  return {
    ...envelope,
    snapshot: structuredClone(envelope.snapshot),
  }
}

function parseEnvelope(value: string | null, expectedKey: string): WorkspaceCacheEnvelope | undefined {
  if (!value) return undefined
  try {
    const parsed = JSON.parse(value) as Partial<WorkspaceCacheEnvelope>
    if (parsed.version !== CACHE_VERSION || parsed.key !== expectedKey || typeof parsed.storedAt !== 'number' || !parsed.snapshot) return undefined
    return parsed as WorkspaceCacheEnvelope
  } catch {
    return undefined
  }
}

/** Read a fresh or recently-stale remote snapshot, if one is available. */
export function readWorkspaceCache(filmId: string, revisionId: string, now = Date.now()): WorkspaceCacheEntry | null {
  const key = cacheKey(filmId, revisionId)
  let envelope = memoryCache.get(key)
  if (!envelope) {
    const storage = browserStorage()
    envelope = parseEnvelope(storage?.getItem(storageKey(key)) ?? null, key)
    if (envelope) memoryCache.set(key, envelope)
  }
  if (!envelope) return null

  const ageMs = Math.max(0, now - envelope.storedAt)
  if (ageMs > WORKSPACE_CACHE_MAX_STALE_MS) {
    invalidateWorkspaceCache(filmId, revisionId)
    return null
  }
  return {
    snapshot: structuredClone(envelope.snapshot),
    ageMs,
    isFresh: ageMs <= WORKSPACE_CACHE_TTL_MS,
  }
}

/** Store only an authoritative ClickHouse/MCP response, never local fallback data. */
export function writeWorkspaceCache(snapshot: WorkspaceSnapshot, storedAt = Date.now()): boolean {
  if (!isCacheable(snapshot)) return false
  const key = cacheKey(snapshot.filmId, snapshot.revisionId)
  const envelope: WorkspaceCacheEnvelope = {
    version: CACHE_VERSION,
    key,
    storedAt,
    snapshot: structuredClone(snapshot),
  }
  memoryCache.set(key, envelope)
  const storage = browserStorage()
  try {
    storage?.setItem(storageKey(key), JSON.stringify(envelope))
  } catch {
    // Private browsing or a full session store should not block the workspace.
  }
  return true
}

/** Invalidate one workspace or all cached workspaces after a mutation. */
export function invalidateWorkspaceCache(filmId?: string, revisionId?: string): void {
  const storage = browserStorage()
  if (filmId !== undefined && revisionId !== undefined) {
    const key = cacheKey(filmId, revisionId)
    memoryCache.delete(key)
    try { storage?.removeItem(storageKey(key)) } catch { /* unavailable storage */ }
    return
  }

  memoryCache.clear()
  if (!storage) return
  try {
    const keys: string[] = []
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index)
      if (key?.startsWith(`${STORAGE_PREFIX}:`)) keys.push(key)
    }
    keys.forEach((key) => storage.removeItem(key))
  } catch {
    // Storage is an optimization; failure simply leaves the in-memory cache clear.
  }
}

export function formatWorkspaceCacheAge(ageMs: number): string {
  if (ageMs < 1_000) return 'NOW'
  if (ageMs < 60_000) return `${Math.max(1, Math.round(ageMs / 1_000))}S AGO`
  return `${Math.max(1, Math.round(ageMs / 60_000))}M AGO`
}

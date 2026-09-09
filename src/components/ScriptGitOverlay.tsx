import { useEffect, useMemo, useState } from 'react'
import { formatClock } from '../lib/workspace'
import { loadScriptGit } from '../lib/api'
import type { ScriptGitDocument, ScriptGitRevision, WorkspaceNode, WorkspaceSnapshot } from '../lib/contracts'

const SOURCE_KEY = 'clio-script-git-source'
const DEFAULT_SOURCE = 'https://github.com/owner/repository/blob/main/script.fountain'

type Props = {
  snapshot: WorkspaceSnapshot
  onApplied: () => void
  onClose: () => void
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'GitHub could not load this script.'
}

function dateLabel(value: string | undefined): string {
  if (!value) return 'DATE —'
  const match = value.match(/^\d{4}-\d{2}-\d{2}/)
  return match?.[0] ?? value.slice(0, 10)
}

function sizeLabel(value: number | undefined): string {
  if (!value || value < 1024) return `${value ?? 0} B`
  return `${(value / 1024).toFixed(1)} KB`
}

function revisionButtonLabel(revision: ScriptGitRevision): string {
  return revision.selected ? 'CURRENT' : 'LOAD'
}

export function ScriptGitOverlay({ snapshot, onApplied, onClose }: Props) {
  const [source, setSource] = useState(() => {
    try { return window.localStorage.getItem(SOURCE_KEY) ?? snapshot.scriptGit?.htmlUrl ?? DEFAULT_SOURCE } catch { return snapshot.scriptGit?.htmlUrl ?? DEFAULT_SOURCE }
  })
  const [ref, setRef] = useState(snapshot.scriptGit?.ref ?? '')
  const [path, setPath] = useState(snapshot.scriptGit?.path ?? '')
  const [document, setDocument] = useState<ScriptGitDocument | undefined>(undefined)
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (snapshot.scriptGit && !document) {
      setSource(snapshot.scriptGit.htmlUrl ?? `https://github.com/${snapshot.scriptGit.repository}`)
      setRef(snapshot.scriptGit.ref)
      setPath(snapshot.scriptGit.path)
    }
  }, [document, snapshot.scriptGit])

  const preview = useMemo(() => {
    if (!document?.content) return ''
    const limit = 2600
    return document.content.length > limit ? `${document.content.slice(0, limit)}\n…` : document.content
  }, [document?.content])

  const diff = useMemo(() => {
    if (!document) return undefined
    const current = snapshot.graph.nodes.filter((node) => node.data.kind === 'scene')
    const incoming = document.nodes.filter((node) => node.data.kind === 'scene')
    const key = (node: WorkspaceNode) => node.data.sceneNumber || node.data.title
    const currentMap = new Map(current.map((node) => [key(node), node]))
    const incomingMap = new Map(incoming.map((node) => [key(node), node]))
    let changed = 0
    for (const [sceneKey, next] of incomingMap) {
      const previous = currentMap.get(sceneKey)
      if (previous && [previous.data.title, previous.data.scriptText, previous.data.startSeconds, previous.data.endSeconds].join('|') !== [next.data.title, next.data.scriptText, next.data.startSeconds, next.data.endSeconds].join('|')) changed += 1
    }
    return {
      added: [...incomingMap.keys()].filter((sceneKey) => !currentMap.has(sceneKey)).length,
      removed: [...currentMap.keys()].filter((sceneKey) => !incomingMap.has(sceneKey)).length,
      changed,
      durationDelta: document.parsed.durationSeconds - snapshot.totalDurationSeconds,
    }
  }, [document, snapshot])

  const load = async (requestedRef?: string) => {
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const next = await loadScriptGit(source.trim(), (requestedRef ?? ref.trim()) || undefined, path.trim() || undefined)
      setDocument(next)
      setRef(next.ref)
      setPath(next.path)
      try { window.localStorage.setItem(SOURCE_KEY, source.trim()) } catch { /* private browsing */ }
      setNotice(`LOADED ${next.shortSha} · ${next.parsed.sceneCount} SCENES`)
    } catch (loadError) {
      setError(errorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }

  const apply = async () => {
    if (!document) return
    setApplying(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch('/api/script-git/apply', {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source: document.htmlUrl ?? source.trim(),
          ref: document.ref,
          path: document.path,
          sha: document.sha,
          actor: 'EDITORIAL',
          runtime_mode: 'simulation',
          document,
        }),
      })
      const payload = await response.json().catch(() => ({})) as Record<string, unknown>
      if (!response.ok) {
        const detail = payload.detail && typeof payload.detail === 'object' ? payload.detail as Record<string, unknown> : {}
        throw new Error(String(detail.message ?? payload.message ?? `Apply failed (${response.status})`))
      }
      setNotice('APPLIED TO SCRIPT MAP')
      onApplied()
    } catch (applyError) {
      setError(errorMessage(applyError))
    } finally {
      setApplying(false)
    }
  }

  return (
    <section id="script-git-overlay" className="fg-git-overlay" role="dialog" aria-modal="false" aria-label="Script Git" data-testid="script-git-overlay" aria-busy={loading || applying}>
      <header className="fg-git-overlay__head">
        <div>
          <span className="fg-label">SCRIPT GIT</span>
          <span className="fg-micro">GITHUB · HUMAN APPLY</span>
        </div>
        <button type="button" className="fg-overlay-close" onClick={onClose} aria-label="Close Script Git">×</button>
      </header>

      <form className="fg-git-connect" onSubmit={(event) => { event.preventDefault(); void load() }}>
        <label htmlFor="git-source"><span className="fg-label">GITHUB FILE OR REPOSITORY</span><input id="git-source" value={source} onChange={(event) => setSource(event.target.value)} placeholder="https://github.com/owner/repo/blob/main/script.fountain" autoFocus /></label>
        <div className="fg-git-connect__row">
          <label htmlFor="git-ref"><span className="fg-label">REF</span><input id="git-ref" value={ref} onChange={(event) => setRef(event.target.value)} placeholder="main or commit SHA" /></label>
          <label htmlFor="git-path"><span className="fg-label">PATH (IF REPO URL)</span><input id="git-path" value={path} onChange={(event) => setPath(event.target.value)} placeholder="script.fountain" /></label>
          <button type="submit" className="fg-action" disabled={loading}>{loading ? 'LOADING…' : 'LOAD'}</button>
        </div>
        <p className="fg-git-hint">PUBLIC FILES WORK WITHOUT A TOKEN · PRIVATE FILES USE CLIO_GITHUB_TOKEN</p>
      </form>

      {error ? <p className="fg-git-error" role="alert">{error}</p> : null}
      {notice ? <p className="fg-git-notice" role="status">{notice}</p> : null}

      {document ? (
        <>
          <section className="fg-git-summary" aria-label="Loaded GitHub script">
            <div className="fg-git-summary__title"><span className="fg-chip fg-chip--github">GITHUB</span><strong>{document.repository}</strong><a href={document.htmlUrl} target="_blank" rel="noreferrer">OPEN ↗</a></div>
            <span className="fg-git-summary__path">{document.path} · {document.ref} · {document.shortSha}</span>
            <div className="fg-git-summary__stats"><span>{document.parsed.sceneCount} SCENES</span><span>{document.parsed.beatCount} BEATS</span><span>{document.parsed.timingEstimated ? '~' : ''}{formatClock(document.parsed.durationSeconds)}</span><span>{sizeLabel(document.size)}</span></div>
            {document.parsed.timingEstimated ? <span className="fg-git-summary__estimate">~ TIMING ESTIMATED FROM SCRIPT LENGTH</span> : null}
          </section>

          <section className="fg-git-history" aria-label="GitHub revision history">
            <div className="fg-section-line"><span className="fg-label">REVISION HISTORY / {document.revisions.length}</span><span className="fg-micro">COMMIT → MAP</span></div>
            <div className="fg-git-history__list">
              {document.revisions.map((revision) => (
                <div className={`fg-git-revision ${revision.selected ? 'is-current' : ''}`} key={revision.sha}>
                  <button type="button" className="fg-git-revision__main" onClick={() => void load(revision.sha)} disabled={loading} aria-label={`Load revision ${revision.shortSha}`}>
                    <span className="fg-git-revision__sha">{revision.shortSha}</span>
                    <span className="fg-git-revision__message">{revision.message}</span>
                    <span className="fg-git-revision__meta">{revision.author} · {dateLabel(revision.committedAt)}</span>
                  </button>
                  <span className="fg-git-revision__action">{revisionButtonLabel(revision)}</span>
                </div>
              ))}
            </div>
          </section>

          {diff ? (
            <section className="fg-git-diff" aria-label="Script map diff">
              <div className="fg-section-line"><span className="fg-label">MAP DIFF</span><span className="fg-micro">CURRENT → LOADED</span></div>
              <div className="fg-git-diff__grid">
                <span><b>{diff.changed}</b> CHANGED</span>
                <span><b>{diff.added}</b> ADDED</span>
                <span><b>{diff.removed}</b> REMOVED</span>
                <span><b>{diff.durationDelta === 0 ? '—' : `${diff.durationDelta > 0 ? '+' : ''}${formatClock(Math.abs(diff.durationDelta))}`}</b> RUNTIME</span>
              </div>
            </section>
          ) : null}

          <section className="fg-git-preview" aria-label="Script preview">
            <div className="fg-section-line"><span className="fg-label">FILE PREVIEW</span><span className="fg-micro">READ ONLY</span></div>
            <pre>{preview}</pre>
          </section>

          <footer className="fg-git-overlay__foot">
            <span className="fg-git-provenance">GITHUB · {document.shortSha} · {document.provenance.source.toUpperCase()}</span>
            <button type="button" className="fg-action" onClick={() => void apply()} disabled={applying}>{applying ? 'APPLYING…' : 'APPLY TO MAP'}</button>
          </footer>
        </>
      ) : (
        <div className="fg-git-empty"><span className="fg-git-empty__mark">↳</span><strong>BRING THE SCRIPT HISTORY INTO THE MAP.</strong><span>Load a Fountain, Markdown, or plain-text screenplay from GitHub. Select a commit to inspect it, then apply it deliberately.</span></div>
      )}
    </section>
  )
}

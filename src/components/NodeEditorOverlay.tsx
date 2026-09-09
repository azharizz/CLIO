import { useEffect, useMemo, useState } from 'react'
import type { GraphNodeDraft, WorkspaceNode } from '../lib/contracts'
import { formatClock } from '../lib/workspace'

type EditorMode = 'create' | 'edit'

type Props = {
  mode: EditorMode
  node?: WorkspaceNode | undefined
  defaultKind?: 'scene' | 'beat' | undefined
  defaultParentId?: string | undefined
  scenes: WorkspaceNode[]
  saving?: boolean
  error?: string
  onSave: (draft: GraphNodeDraft) => void
  onClose: () => void
}

function draftFor(props: Props): GraphNodeDraft {
  const node = props.node
  const kind = node?.data.kind === 'beat' || props.defaultKind === 'beat' ? 'beat' : 'scene'
  const parent = node?.data.parentSceneId ?? props.defaultParentId ?? props.scenes[props.scenes.length - 1]?.id
  // A new child beat should inherit the selected scene's time envelope. The
  // previous implementation used the last scene in the film, which opened an
  // Timing validation remains explicit for long-form scenes such as Titanic
  // SC 17, whose beats must stay inside 01:50:00→01:58:30.
  const parentScene = kind === 'beat' && parent
    ? props.scenes.find((scene) => scene.id === parent)
    : undefined
  const start = node?.data.startSeconds
    ?? (kind === 'beat' ? (parentScene?.data.startSeconds ?? 0) : (props.scenes.at(-1)?.data.endSeconds ?? 0))
  const end = node?.data.endSeconds
    ?? (kind === 'beat' ? (parentScene?.data.endSeconds ?? start + 60) : start + 60)
  return {
    kind,
    ...(node?.data.sceneNumber ? { sceneNumber: node.data.sceneNumber } : {}),
    ...(node?.data.beatNumber ? { beatNumber: node.data.beatNumber } : {}),
    ...(parent ? { parentSceneId: parent } : {}),
    heading: node?.data.title ?? '',
    scriptText: node?.data.scriptText ?? node?.data.detail ?? '',
    narrationText: node?.data.narrationText ?? '',
    startSeconds: start,
    endSeconds: end,
  }
}

export function NodeEditorOverlay({ mode, node, defaultKind, defaultParentId, scenes, saving = false, error, onSave, onClose }: Props) {
  const [draft, setDraft] = useState<GraphNodeDraft>(() => draftFor({ mode, node, defaultKind, defaultParentId, scenes, onSave, onClose }))
  const [localError, setLocalError] = useState('')
  useEffect(() => {
    setDraft(draftFor({ mode, node, defaultKind, defaultParentId, scenes, onSave, onClose }))
    setLocalError('')
  }, [mode, node?.id, defaultKind, defaultParentId, scenes.length]) // eslint-disable-line react-hooks/exhaustive-deps
  const duration = useMemo(() => Math.max(0, draft.endSeconds - draft.startSeconds), [draft.endSeconds, draft.startSeconds])
  const set = <K extends keyof GraphNodeDraft>(key: K, value: GraphNodeDraft[K]) => setDraft((current) => ({ ...current, [key]: value }))
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setLocalError('')
    if (!draft.heading.trim() || !draft.scriptText.trim()) {
      setLocalError('Heading and script text are required.')
      return
    }
    if (draft.endSeconds <= draft.startSeconds) {
      setLocalError('End time must be greater than start time.')
      return
    }
    if (draft.kind === 'beat' && !draft.parentSceneId) {
      setLocalError('Choose a parent scene.')
      return
    }
    onSave(draft)
  }

  return (
    <section className="fg-editor-overlay" role="dialog" aria-modal="true" aria-label={`${mode === 'create' ? 'Create' : 'Edit'} script node`} data-testid="node-editor">
      <form className="fg-editor" onSubmit={submit}>
        <header className="fg-editor__head">
          <div>
            <span className="fg-label">{mode === 'create' ? 'NEW NODE' : 'EDIT NODE'}</span>
            <span className="fg-micro">SCRIPT · NARRATION · TIME</span>
          </div>
          <button type="button" className="fg-overlay-close" onClick={onClose} aria-label="Close node editor">×</button>
        </header>
        <div className="fg-editor__body">
          {mode === 'create' ? (
            <div className="fg-editor__switch" role="group" aria-label="Node type">
              <button type="button" className={draft.kind === 'scene' ? 'is-active' : ''} onClick={() => set('kind', 'scene')}>SCENE</button>
              <button type="button" className={draft.kind === 'beat' ? 'is-active' : ''} onClick={() => set('kind', 'beat')}>BEAT</button>
            </div>
          ) : <span className="fg-editor__locked">{draft.kind.toUpperCase()} · IDENTITY LOCKED</span>}

          <div className="fg-editor__grid">
            {draft.kind === 'scene' ? (
              <div className="fg-editor__field"><label htmlFor="node-scene-number"><span>SCENE NO.</span></label><input id="node-scene-number" value={draft.sceneNumber ?? ''} readOnly={mode === 'edit'} onChange={(event) => set('sceneNumber', event.target.value)} placeholder="50" /></div>
            ) : (
              <div className="fg-editor__field"><label htmlFor="node-parent-scene"><span>PARENT SCENE</span></label><select id="node-parent-scene" value={draft.parentSceneId ?? ''} onChange={(event) => set('parentSceneId', event.target.value)}>
                <option value="">Choose scene</option>
                {scenes.map((scene) => <option value={scene.id} key={scene.id}>SC {scene.data.sceneNumber} · {scene.data.title}</option>)}
              </select></div>
            )}
            {draft.kind === 'beat' ? <div className="fg-editor__field"><label htmlFor="node-beat-number"><span>BEAT NO.</span></label><input id="node-beat-number" type="number" min="1" value={draft.beatNumber ?? ''} onChange={(event) => set('beatNumber', event.target.value ? Number(event.target.value) : undefined)} placeholder="1" /></div> : null}
          </div>
          <div className="fg-editor__field"><label htmlFor="node-heading"><span>HEADING</span></label><input id="node-heading" required value={draft.heading} onChange={(event) => set('heading', event.target.value)} placeholder="INT. NEW ROOM — NIGHT" /></div>
          <div className="fg-editor__field"><label htmlFor="node-script-text"><span>SCRIPT TEXT</span></label><textarea id="node-script-text" required rows={3} value={draft.scriptText} onChange={(event) => set('scriptText', event.target.value)} placeholder="What happens on screen?" /></div>
          <div className="fg-editor__field"><label htmlFor="node-narration"><span>NARRATION</span></label><textarea id="node-narration" rows={2} value={draft.narrationText} onChange={(event) => set('narrationText', event.target.value)} placeholder="Optional spoken or voice-over line" /></div>
          <div className="fg-editor__timing">
            <div className="fg-editor__field"><label htmlFor="node-start"><span>START (SEC)</span></label><input id="node-start" type="number" min="0" value={draft.startSeconds} onChange={(event) => set('startSeconds', Number(event.target.value))} /></div>
            <div className="fg-editor__field"><label htmlFor="node-end"><span>END (SEC)</span></label><input id="node-end" type="number" min="1" value={draft.endSeconds} onChange={(event) => set('endSeconds', Number(event.target.value))} /></div>
            <div><span>DURATION</span><strong>{formatClock(duration)}</strong></div>
          </div>
          {localError || error ? <p className="fg-editor__error" role="alert">{localError || error}</p> : null}
        </div>
        <footer className="fg-editor__foot">
          <button type="button" className="fg-button-quiet" onClick={onClose}>CANCEL</button>
          <button type="submit" className="fg-action" disabled={saving}>{saving ? 'SAVING…' : mode === 'create' ? 'CREATE NODE' : 'SAVE CHANGES'}</button>
        </footer>
      </form>
    </section>
  )
}

import { useState } from 'react'

const steps = [
  {
    mark: '01 / MAP',
    title: 'START WITH THE SCRIPT',
    body: 'Scenes are the parent nodes. Each one keeps its script, narration, start, end, and duration in view.',
    signal: 'SCENE → NARRATION → TIME',
  },
  {
    mark: '02 / TRACE',
    title: 'OPEN THE COMPLEX PARTS',
    body: 'Long scenes split into timed child beats. Select a beat to see the exact text and what it changes downstream.',
    signal: 'SC 47 → B01 B02 B03 B04',
  },
  {
    mark: '03 / CONTROL',
    title: 'ASK, THEN DECIDE',
    body: 'The agent proposes affected, removed, or possible nodes. You own every create, edit, and delete.',
    signal: 'HUMAN DECISION · NO AUTO-WRITES',
  },
] as const

export function OnboardingOverlay({ onDone, onCreate }: { onDone: () => void; onCreate: () => void }) {
  const [step, setStep] = useState(0)
  const current = steps[step]!
  const finish = () => onDone()

  return (
    <section className="fg-onboarding" role="dialog" aria-modal="true" aria-label="CLIO onboarding" data-testid="onboarding">
      <div className="fg-onboarding__panel">
        <header className="fg-onboarding__head">
          <div>
            <span className="fg-label">CLIO / FIRST RUN</span>
            <span className="fg-micro">LOCAL DEMO · SCRIPT MAP</span>
          </div>
          <button type="button" className="fg-overlay-close" onClick={finish} aria-label="Skip onboarding">×</button>
        </header>
        <div className="fg-onboarding__body">
          <span className="fg-onboarding__mark">{current.mark}</span>
          <h1>{current.title}</h1>
          <p>{current.body}</p>
          <div className="fg-onboarding__signal">{current.signal}</div>
          <div className="fg-onboarding__steps" aria-label={`Onboarding step ${step + 1} of ${steps.length}`}>
            {steps.map((item, index) => <span key={item.mark} className={index === step ? 'is-active' : index < step ? 'is-done' : ''} />)}
          </div>
        </div>
        <footer className="fg-onboarding__foot">
          <button type="button" className="fg-button-quiet" onClick={finish}>SKIP</button>
          <div>
            {step === 0 ? <button type="button" className="fg-button-quiet" onClick={onCreate}>CREATE NODE</button> : null}
            <button type="button" className="fg-action" onClick={() => step === steps.length - 1 ? finish() : setStep((value) => value + 1)}>
              {step === steps.length - 1 ? 'ENTER MAP' : 'NEXT'}
            </button>
          </div>
        </footer>
      </div>
    </section>
  )
}

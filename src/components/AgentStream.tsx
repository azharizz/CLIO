export interface StreamEvent {
  id: string
  stage: string
  label: string
  detail: string
  tone: 'trace' | 'breach' | 'resolved' | 'split' | 'pending'
  at: string
}

export function addEvent(current: StreamEvent[], next: StreamEvent) {
  const deduped = current.filter((event) => event.id !== next.id)
  return [next, ...deduped].slice(0, 5)
}

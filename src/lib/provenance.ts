import type { Provenance, ProvenanceSource, ValueWithProvenance } from './contracts'

export const provenance = (source: ProvenanceSource, label: string, detail?: string): Provenance => ({ source, label, ...(detail ? { detail } : {}) })

export const withProvenance = <T>(value: T, source: ProvenanceSource, label: string, detail?: string): ValueWithProvenance<T> => ({
  value,
  provenance: provenance(source, label, detail),
})

export function provenanceLabel(value: Provenance | undefined): string {
  return value?.label ?? 'UNSPECIFIED'
}

export function provenanceSource(value: Provenance | undefined): ProvenanceSource {
  return value?.source ?? 'computed'
}

import rawStoryboard from '../../data/titanic_storyboard.json'
import type { Tone } from './contracts'

export type TitanicBeatSeed = {
  number: number
  title: string
  text: string
  narration: string
  start: number
  end: number
}

export type TitanicSceneSeed = {
  number: string
  heading: string
  text: string
  narration: string
  start: number
  end: number
  status: Tone
  beats: TitanicBeatSeed[]
}

type RawStoryboard = {
  version: string
  durations: number[]
  scenes: Array<{
    number: string
    heading: string
    summary: string
    narration: string
    status: Tone
    beats: Array<{ title: string; text: string; narration: string }>
  }>
}

const storyboard = rawStoryboard as RawStoryboard

export const TITANIC_SCENE_SEEDS: TitanicSceneSeed[] = storyboard.scenes.map((scene, index) => {
  const start = storyboard.durations.slice(0, index).reduce((total, duration) => total + duration, 0)
  const end = start + storyboard.durations[index]!
  const span = end - start
  return {
    number: scene.number,
    heading: scene.heading,
    text: scene.summary,
    narration: scene.narration,
    status: scene.status,
    start,
    end,
    beats: scene.beats.map((beat, beatIndex) => {
      const beatStart = start + Math.floor((span * beatIndex) / 5)
      const beatEnd = beatIndex === 4 ? end : start + Math.floor((span * (beatIndex + 1)) / 5)
      return { number: beatIndex + 1, ...beat, start: beatStart, end: beatEnd }
    }),
  }
})

export const TITANIC_STORYBOARD_VERSION = storyboard.version
export const TITANIC_TOTAL_DURATION_SECONDS = storyboard.durations.reduce((total, duration) => total + duration, 0)
export const TITANIC_TOTAL_SCENE_COUNT = TITANIC_SCENE_SEEDS.length
export const TITANIC_TOTAL_BEAT_COUNT = TITANIC_SCENE_SEEDS.reduce((total, scene) => total + scene.beats.length, 0)


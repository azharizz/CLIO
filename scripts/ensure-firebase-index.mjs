import { copyFile, readdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const clientDir = join(process.cwd(), 'dist', 'client')
const entry = (await readdir(join(clientDir, 'assets'))).find((name) => /^index-.*\.js$/.test(name))
const css = (await readdir(join(clientDir, 'assets'))).find((name) => /^index-.*\.css$/.test(name))
if (!entry) throw new Error('TanStack client entry was not emitted')
const stylesheet = css ? `<link rel="stylesheet" href="/assets/${css}"/>` : ''
if (css) await copyFile(join(clientDir, 'assets', css), join(clientDir, 'clio.css'))
const html = `<!doctype html><html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><meta name="theme-color" content="#000000"/><meta name="description" content="CLIO — Continuity & Lineage Intelligence Operator"/><title>CLIO — Continuity &amp; Lineage Intelligence Operator</title><link rel="icon" href="/clio-cut-monogram.png" type="image/png"/>${stylesheet}</head><body><script type="module" src="/assets/${entry}"></script></body></html>`
await writeFile(join(clientDir, 'index.html'), html)
console.log(`Firebase static entry written: ${entry}`)

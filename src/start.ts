import { createCsrfMiddleware, createStart } from '@tanstack/react-start'

const csrfMiddleware = createCsrfMiddleware({
  filter: (ctx) => ctx.handlerType === 'serverFn',
  // Local server-function calls can be made without browser fetch metadata;
  // when metadata is present, same-origin validation still applies.
  allowRequestsWithoutOriginCheck: true,
})

export const startInstance = createStart(() => ({
  requestMiddleware: [csrfMiddleware],
}))

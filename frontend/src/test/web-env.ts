import type { Environment } from 'vitest/environments'

// Node with the browser build of .vue files (render functions, not SSR), for the page tests that
// mount components with the in-memory renderer of src/test/renderer.ts. No DOM library is needed.
export default <Environment>{
  name: 'node-web',
  transformMode: 'web',
  setup() {
    return { teardown() {} }
  },
}

import { createRenderer, nextTick, type Component } from 'vue'

// A tiny in-memory Vue renderer for the page tests (no DOM library): elements are plain objects,
// event listeners stay as `on*` props, and tests read text and attributes and call the listeners.
export interface TestNode {
  tag: string
  props: Record<string, unknown>
  children: TestNode[]
  parent: TestNode | null
  text: string
}

function node(tag: string, text = ''): TestNode {
  return { tag, props: {}, children: [], parent: null, text }
}

function detach(child: TestNode) {
  const parent = child.parent
  if (!parent) return
  parent.children.splice(parent.children.indexOf(child), 1)
  child.parent = null
}

const { createApp } = createRenderer<TestNode, TestNode>({
  createElement: (tag) => node(tag),
  createText: (text) => node('#text', text),
  createComment: (text) => node('#comment', text),
  setText: (n, text) => {
    n.text = text
  },
  setElementText: (el, text) => {
    el.children.forEach((c) => (c.parent = null))
    el.children = []
    if (text) {
      const t = node('#text', text)
      t.parent = el
      el.children.push(t)
    }
  },
  insert: (child, parent, anchor) => {
    detach(child)
    const at = anchor ? parent.children.indexOf(anchor) : -1
    if (at < 0) parent.children.push(child)
    else parent.children.splice(at, 0, child)
    child.parent = parent
  },
  remove: detach,
  parentNode: (n) => n.parent,
  nextSibling: (n) => {
    const siblings = n.parent?.children ?? []
    return siblings[siblings.indexOf(n) + 1] ?? null
  },
  patchProp: (el, key, _prev, next) => {
    el.props[key] = next
  },
})

export function textOf(n: TestNode): string {
  if (n.tag === '#text') return n.text
  if (n.tag === '#comment') return ''
  return n.children.map(textOf).join('')
}

export function findAll(n: TestNode, test: (n: TestNode) => boolean): TestNode[] {
  return [...(test(n) ? [n] : []), ...n.children.flatMap((c) => findAll(c, test))]
}

export function byAttr(root: TestNode, attr: string, value?: string): TestNode[] {
  return findAll(root, (n) => attr in n.props && (value === undefined || n.props[attr] === value))
}

export async function flush() {
  for (let i = 0; i < 10; i++) {
    await Promise.resolve()
    await nextTick()
  }
}

export async function mount(
  component: Component,
  setup: (app: ReturnType<typeof createApp>) => void = () => {},
) {
  const root = node('root')
  const app = createApp(component)
  setup(app)
  app.mount(root)
  await flush()
  return { root, app, text: () => textOf(root) }
}

export async function click(n: TestNode) {
  const handler = n.props.onClick as ((e?: unknown) => unknown) | undefined
  if (!handler) throw new Error(`no click handler on <${n.tag}>`)
  await handler({ preventDefault() {} })
  await flush()
}

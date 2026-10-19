import { get, post } from './api'

// CARD's operator endpoints (card/materials.py); the server checks every call.

export interface Machine {
  name: string
  equipment_name: string
  project: string | null
}

export interface RequestLine {
  kind: 'Part' | 'Tool'
  item_code: string | null
  description: string | null
  qty: number
}

export interface NeedsRequest {
  name: string
  equipment_name: string
  request_date: string
  review_status: string
  docstatus: number
  items: RequestLine[]
}

export interface PortalContext {
  employee: string | null
  allowed: boolean
  machines: Machine[]
  requests: NeedsRequest[]
}

export interface Item {
  item_code: string
  item_name: string
  stock_uom: string
}

export interface DraftLine {
  key: number
  kind: 'Part' | 'Tool'
  item_code: string
  item_name: string
  description: string
  qty: number | null
  reason: string
}

let lastKey = 0

export function newLine(): DraftLine {
  return {
    key: ++lastKey,
    kind: 'Part',
    item_code: '',
    item_name: '',
    description: '',
    qty: 1,
    reason: '',
  }
}

// A line the operator left untouched is skipped; a started line needs an item (picked or
// described) and a quantity, so nothing he typed is dropped without telling him.
export function incompleteLines(lines: DraftLine[]): number[] {
  return lines.flatMap((l, i) => {
    const named = !!(l.item_code || l.description.trim())
    const started = named || !!l.reason.trim()
    return started && !(named && Number(l.qty) > 0) ? [i + 1] : []
  })
}

// A line is sent when it names an item (picked or described) and has a quantity.
export function sendableLines(lines: DraftLine[]) {
  return lines
    .filter((l) => (l.item_code || l.description.trim()) && Number(l.qty) > 0)
    .map((l) => ({
      kind: l.kind,
      item_code: l.item_code || null,
      description: l.item_code ? l.item_name : l.description.trim(),
      qty: Number(l.qty),
      reason: l.reason.trim(),
    }))
}

let portal: Promise<PortalContext> | null = null

export function getPortal(refresh = false): Promise<PortalContext> {
  if (!portal || refresh) {
    portal = get<PortalContext>('card.materials.get_portal_context')
    portal.catch(() => (portal = null))
  }
  return portal
}

export function searchItems(txt: string): Promise<Item[]> {
  return get<Item[]>('card.materials.search_items', { txt })
}

export function submitNeeds(equipment: string, lines: DraftLine[], notes: string) {
  return post<string>('card.materials.submit_needs', {
    equipment,
    items: JSON.stringify(sendableLines(lines)),
    notes,
  })
}

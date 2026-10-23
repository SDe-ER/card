import { describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ get: vi.fn(), post: vi.fn().mockResolvedValue('ENR-0001') }))

import { post } from './api'
import { incompleteLines, newLine, sendableLines, submitNeeds } from './needs'

describe('sendableLines', () => {
  it('drops empty lines and lines without a quantity', () => {
    const lines = [
      newLine(),
      { ...newLine(), description: 'Hydraulic hose', qty: 0 },
      { ...newLine(), description: '  ', qty: 2 },
    ]
    expect(sendableLines(lines)).toEqual([])
  })

  it('sends a picked item with its name as the description', () => {
    const line = {
      ...newLine(),
      item_code: 'OIL-15W40',
      item_name: 'Engine oil',
      qty: 4,
      reason: ' change ',
    }
    expect(sendableLines([line])).toEqual([
      {
        kind: 'Part',
        item_code: 'OIL-15W40',
        description: 'Engine oil',
        qty: 4,
        reason: 'change',
      },
    ])
  })

  it('sends a described tool without an item code', () => {
    const line = { ...newLine(), kind: 'Tool' as const, description: ' Torque wrench ', qty: 1 }
    expect(sendableLines([line])).toEqual([
      { kind: 'Tool', item_code: null, description: 'Torque wrench', qty: 1, reason: '' },
    ])
  })
})

describe('incompleteLines', () => {
  it('skips untouched lines and names started lines missing an item or a quantity', () => {
    const lines = [
      { ...newLine(), description: 'Air filter', qty: 2 },
      { ...newLine(), description: 'Hydraulic hose', qty: 0 },
      newLine(),
      { ...newLine(), reason: 'leaking', qty: 1 },
      { ...newLine(), item_code: 'OIL-15W40', item_name: 'Engine oil', qty: null },
    ]
    expect(incompleteLines(lines)).toEqual([2, 4, 5])
  })

  it('accepts complete lines', () => {
    expect(incompleteLines([{ ...newLine(), item_code: 'X', item_name: 'X', qty: 1 }])).toEqual([])
  })
})

// CARD Mobile offered no kind at all before (TabButtons got `buttons`, frappe-ui 1.0.2 reads
// `options`), so every line went out as a part and an operator could not ask for a tool.
describe('line kind', () => {
  it('sends the chosen kind of every line to the server', async () => {
    const tool = {
      ...newLine(),
      kind: 'Tool' as const,
      item_code: 'WRENCH',
      item_name: 'Torque wrench',
      qty: 1,
    }
    const part = { ...newLine(), description: 'Hydraulic hose', qty: 2 }
    vi.mocked(post).mockClear()
    await submitNeeds('CEQ-0001', [tool, part], '')
    const [method, args] = vi.mocked(post).mock.lastCall as [string, Record<string, string>]
    expect(method).toBe('card.materials.submit_needs')
    expect(JSON.parse(args.items).map((l: { kind: string }) => l.kind)).toEqual(['Tool', 'Part'])
  })
})

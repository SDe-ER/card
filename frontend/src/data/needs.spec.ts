import { describe, expect, it } from 'vitest'
import { newLine, sendableLines } from './needs'

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

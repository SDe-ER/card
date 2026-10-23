import { describe, expect, it } from 'vitest'
import { incompleteLines, linesWithoutFitReason, newLine, sendableLines } from './needs'

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
        fit_reason: '',
      },
    ])
  })

  it('sends a described tool without an item code', () => {
    const line = { ...newLine(), kind: 'Tool' as const, description: ' Torque wrench ', qty: 1 }
    expect(sendableLines([line])).toEqual([
      {
        kind: 'Tool',
        item_code: null,
        description: 'Torque wrench',
        qty: 1,
        reason: '',
        fit_reason: '',
      },
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

describe('linesWithoutFitReason', () => {
  const picked = { ...newLine(), item_code: 'FILTER', item_name: 'Filter', qty: 1 }

  it('asks for the reason when the picked item has no confirmed fit', () => {
    const lines = [
      { ...picked, fit: 'confirmed_machine' as const },
      { ...picked, fit: 'confirmed_model' as const },
      { ...picked, fit: 'not_compatible' as const },
      { ...picked, fit: 'pending' as const },
      { ...picked, fit: 'unknown' as const },
      { ...picked, fit: 'unknown' as const, fit_reason: 'mechanic asked for it' },
      { ...newLine(), description: 'Hose', qty: 1 },
      { ...picked, fit: null },
    ]
    expect(linesWithoutFitReason(lines)).toEqual([3, 4, 5, 8])
  })

  it('sends the fit reason of a picked item only', () => {
    const lines = [
      { ...picked, fit: 'not_compatible' as const, fit_reason: ' old model part ' },
      { ...newLine(), description: 'Hose', qty: 1, fit_reason: 'ignored' },
    ]
    expect(sendableLines(lines).map((l) => l.fit_reason)).toEqual(['old model part', ''])
  })
})

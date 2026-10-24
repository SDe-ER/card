import { describe, expect, it } from 'vitest'
import {
  isCompatible,
  mergePage,
  needsFitReason,
  PAGE_LENGTH,
  searchParams,
  type CatalogItem,
} from './catalog'

function item(code: string): CatalogItem {
  return {
    item_code: code,
    item_name: code,
    stock_uom: 'Nos',
    image: null,
    item_group: null,
    item_group_label: null,
    brand: null,
    oem: [],
    alternatives: [],
  }
}

describe('searchParams', () => {
  it('sends only the filled filters and the page window', () => {
    expect(searchParams({ txt: '  filter ', item_group: null, brand: 'CAT' }, 40)).toEqual({
      start: '40',
      page_length: String(PAGE_LENGTH),
      txt: 'filter',
      brand: 'CAT',
    })
  })

  it('lists the first page when nothing is typed', () => {
    expect(searchParams({ txt: ' ', item_group: 'Parts', brand: null }, 0)).toEqual({
      start: '0',
      page_length: String(PAGE_LENGTH),
      item_group: 'Parts',
    })
  })
})

describe('searchParams with a machine', () => {
  it('sends the machine, and fits only with a machine', () => {
    const query = { txt: '', item_group: null, brand: null }
    expect(searchParams({ ...query, equipment: 'CEQ-0001', fits: true }, 0)).toMatchObject({
      equipment: 'CEQ-0001',
      fits: '1',
    })
    expect(searchParams({ ...query, equipment: 'CEQ-0001', fits: false }, 0)).not.toHaveProperty(
      'fits',
    )
    expect(searchParams({ ...query, equipment: null, fits: true }, 0)).not.toHaveProperty('fits')
  })
})

describe('fit states', () => {
  it('keeps the four answers apart: only a confirmed fit needs no reason', () => {
    expect(isCompatible('confirmed_machine')).toBe(true)
    expect(isCompatible('confirmed_model')).toBe(true)
    for (const fit of ['not_compatible', 'pending', 'unknown'] as const) {
      expect(isCompatible(fit)).toBe(false)
      expect(needsFitReason(fit)).toBe(true)
    }
    expect(needsFitReason(null)).toBe(true) // not known yet: ask, the server decides
  })
})

describe('mergePage', () => {
  it('adds a next page without repeating rows', () => {
    const merged = mergePage([item('A'), item('B')], [item('B'), item('C')])
    expect(merged.map((i) => i.item_code)).toEqual(['A', 'B', 'C'])
  })
})

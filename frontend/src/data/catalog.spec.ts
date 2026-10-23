import { describe, expect, it } from 'vitest'
import { mergePage, PAGE_LENGTH, searchParams, type CatalogItem } from './catalog'

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

describe('mergePage', () => {
  it('adds a next page without repeating rows', () => {
    const merged = mergePage([item('A'), item('B')], [item('B'), item('C')])
    expect(merged.map((i) => i.item_code)).toEqual(['A', 'B', 'C'])
  })
})

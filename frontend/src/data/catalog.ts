import { get } from './api'

// CARD's catalog endpoints (card/catalog.py): the standard ERPNext Item catalogue, read with the
// user's own rights on the server. No stock, price or supplier is ever returned.

export interface CatalogOem {
  manufacturer: string
  part_no: string
}

export interface CatalogAlternative {
  item_code: string
  item_name: string
}

// The fit of an Item for one machine (card/fitment.py, phase 2b). Four separate answers: a
// confirmed fit (machine or model), Not compatible, Pending review, or no fitment record.
export type Fit =
  | 'confirmed_machine'
  | 'confirmed_model'
  | 'not_compatible'
  | 'pending'
  | 'unknown'

export interface FitResult {
  fit: Fit
  fit_model: string | null
}

export interface CatalogItem {
  item_code: string
  item_name: string
  stock_uom: string
  image: string | null
  item_group: string | null
  item_group_label: string | null
  brand: string | null
  oem: CatalogOem[]
  alternatives: CatalogAlternative[]
  // only when the search names a machine
  fit?: Fit
  fit_model?: string | null
}

export interface CatalogPage {
  items: CatalogItem[]
  has_more: boolean
}

export interface CatalogQuery {
  txt: string
  item_group: string | null
  brand: string | null
  equipment?: string | null
  fits?: boolean
}

export interface FilterOption {
  value: string
  label: string
}

export const PAGE_LENGTH = 20

// Only the filled filters are sent; the server pages the results.
export function searchParams(query: CatalogQuery, start: number): Record<string, string> {
  const params: Record<string, string> = {
    start: String(start),
    page_length: String(PAGE_LENGTH),
  }
  if (query.txt.trim()) params.txt = query.txt.trim()
  if (query.item_group) params.item_group = query.item_group
  if (query.brand) params.brand = query.brand
  if (query.equipment) {
    params.equipment = query.equipment
    if (query.fits) params.fits = '1'
  }
  return params
}

export function searchCatalog(query: CatalogQuery, start = 0): Promise<CatalogPage> {
  return get<CatalogPage>('card.catalog.search', searchParams(query, start))
}

export function filterOptions(kind: 'item_group' | 'brand', txt: string): Promise<FilterOption[]> {
  const params: Record<string, string> = { kind }
  if (txt.trim()) params.txt = txt.trim()
  return get<FilterOption[]>('card.catalog.filter_options', params)
}

// A next page is added once: rows already shown (e.g. after a new item was created) stay single.
export function mergePage(shown: CatalogItem[], page: CatalogItem[]): CatalogItem[] {
  const seen = new Set(shown.map((item) => item.item_code))
  return [...shown, ...page.filter((item) => !seen.has(item.item_code))]
}

// Only a confirmed fit needs no reason on a request line (Owner Q10, decisions C and D).
export function isCompatible(fit: Fit | null | undefined): boolean {
  return fit === 'confirmed_machine' || fit === 'confirmed_model'
}

// an unknown answer (still loading, or the lookup failed) asks for the reason too: the server
// decides at submit and must never find a line without one
export function needsFitReason(fit: Fit | null | undefined): boolean {
  return !isCompatible(fit)
}

export function fitFor(
  equipment: string,
  itemCodes: string[],
): Promise<Record<string, FitResult>> {
  return get<Record<string, FitResult>>('card.fitment.fit_for', {
    equipment,
    items: JSON.stringify(itemCodes),
  })
}

export interface CatalogMachine {
  name: string
  equipment_name: string | null
  model: string | null
}

export function searchMachines(
  txt: string,
  start = 0,
): Promise<{ machines: CatalogMachine[]; has_more: boolean }> {
  const params: Record<string, string> = { start: String(start) }
  if (txt.trim()) params.txt = txt.trim()
  return get('card.fitment.machines', params)
}

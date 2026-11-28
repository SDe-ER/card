import { get, post } from './api'

// CARD Mobile profile and role-based home (issue #357; card/mobile.py). The server decides what a
// role may see: `kpis` is null for an operator and `financial` is null unless the user is a Card
// Manager or System Manager. The client only draws what it receives.

export interface HomeKpis {
  equipment: { active: number; stopped: number; maintenance: number }
  fleet_by_project: { project: string | null; count: number }[]
  requests_to_review: number
  logs_to_review: number
  alerts: { documents_expiring: number }
}

export interface FinancialRow {
  company: string
  currency: string | null
  revenue: number
  cost: number
}

export interface HomeContext {
  reviewer: boolean
  manager: boolean
  kpis: HomeKpis | null
  financial: { month: number; year: number; by_company: FinancialRow[] } | null
}

export interface Profile {
  user: string
  full_name: string
  email: string | null
  phone: string | null
  image: string | null
  employee: { name: string; designation: string | null; branch: string | null } | null
  company: string | null
  currency: string | null
  number_format: string | null
  language: string
  roles: string[]
  card_version: string
}

export const getHomeContext = () => get<HomeContext>('card.mobile.get_home_context')
export const getProfile = () => get<Profile>('card.mobile.get_profile')
export const setLanguage = (language: 'ar' | 'en') =>
  post<string>('card.mobile.set_language', { language })

// Full-precision money, e.g. "128,450.00 SAR": never abbreviated, tabular digits in the template.
export function formatMoney(value: number, currency: string | null): string {
  const number = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
  return currency ? `${number} ${currency}` : number
}

import { get } from './api'

// CARD Mobile management view (issue #358; card/mobile_management.py). The server refuses a
// non-reviewer and leaves money out unless the user is a Card Manager or System Manager.
export const REVIEW_ROLES = ['Card Supervisor', 'Card Manager', 'System Manager']

export const isReviewer = (roles: string[] | undefined) =>
  !!roles?.some((role) => REVIEW_ROLES.includes(role))

export interface ManagementContext {
  ownership: string[]
  status: string[]
  money: boolean
  cards: boolean
}

export interface FleetRow {
  name: string
  equipment_name: string | null
  ownership: string | null
  status: string | null
  operator_name: string | null
  plate_no: string | null
  current_project: string | null
}

export interface CardRow {
  name: string
  equipment: string
  equipment_name: string | null
  project: string | null
  docstatus: number
  working_days: number
  total_working_hours: number
  net_amount?: number
  customer_net_amount?: number
}

export interface ProjectRow {
  project: string | null
  equipment: number
  cards: number
  hours: number
  revenue?: number
  cost?: number
  result?: number
}

const query = (params: Record<string, string | number | undefined>) =>
  Object.fromEntries(
    Object.entries(params)
      .filter(([, value]) => value !== undefined && value !== '')
      .map(([key, value]) => [key, String(value)]),
  )

export const getManagementContext = () =>
  get<ManagementContext>('card.mobile_management.get_management_context')
export const listAllEquipment = (filters: {
  ownership?: string
  project?: string
  status?: string
}) => get<FleetRow[]>('card.mobile_management.list_all_equipment', query(filters))
export const listMonthlyCards = (year?: number, month?: number) =>
  get<CardRow[]>('card.mobile_management.list_monthly_cards', query({ year, month }))
export const listProjects = (year?: number, month?: number) =>
  get<ProjectRow[]>('card.mobile_management.list_projects', query({ year, month }))

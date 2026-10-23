import { describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ get: vi.fn(), post: vi.fn().mockResolvedValue('ENR-0001') }))

import { post } from './api'
import { newLine, submitNeeds } from './needs'

describe('submitNeeds', () => {
  it('sends the chosen kind of every line to the server', async () => {
    const tool = {
      ...newLine(),
      kind: 'Tool' as const,
      item_code: 'WRENCH',
      item_name: 'Torque wrench',
      qty: 1,
    }
    const part = { ...newLine(), description: 'Hydraulic hose', qty: 2 }
    await submitNeeds('CEQ-0001', [tool, part], '')
    const [method, args] = vi.mocked(post).mock.calls[0] as [string, Record<string, string>]
    expect(method).toBe('card.materials.submit_needs')
    expect(JSON.parse(args.items).map((l: { kind: string }) => l.kind)).toEqual(['Tool', 'Part'])
  })
})

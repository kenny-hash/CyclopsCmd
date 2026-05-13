import { describe, expect, it } from 'vitest'
import { isValidIpAddress } from '../validation'

describe('isValidIpAddress', () => {
  it('accepts compressed IPv6 literals with multiple hextets after ::', () => {
    expect(isValidIpAddress('2001:db8::8a2e:370:7334')).toBe(true)
    expect(isValidIpAddress('fe80::1234:5678')).toBe(true)
  })

  it('keeps rejecting malformed IPv6 literals', () => {
    expect(isValidIpAddress('2001:db8:::1')).toBe(false)
    expect(isValidIpAddress('1::2::3')).toBe(false)
    expect(isValidIpAddress('2001:db8::g')).toBe(false)
  })
})

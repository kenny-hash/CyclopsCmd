import { describe, expect, it } from 'vitest'
import { ansiToHtml } from '../ansi-to-html'

describe('ansiToHtml', () => {
  it('escapes HTML special characters when no ANSI style is present', () => {
    expect(ansiToHtml('<script>alert("x")</script> & \'quoted\'')).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#039;quoted&#039;',
    )
  })

  it('converts ANSI color sequences to styled spans and resets styles', () => {
    expect(ansiToHtml('ok \x1b[31mfailed\x1b[0m done')).toBe(
      'ok <span style="color: #A00">failed</span> done',
    )
  })

  it('normalizes terminal whitespace and line endings for browser output', () => {
    expect(ansiToHtml('a\r\nb\tc')).toBe('a<br>b    c')
  })
})

// ansi-to-html.js
// 这个工具用于将ANSI转义序列转换为HTML

// ANSI颜色码到CSS颜色的映射
const ANSI_COLORS = {
    // 标准颜色
    0: 'color: inherit; background-color: inherit', // 重置
    1: 'font-weight: bold',                         // 粗体
    2: 'opacity: 0.8',                              // 暗色
    3: 'font-style: italic',                        // 斜体
    4: 'text-decoration: underline',                // 下划线
    7: 'color: #000; background-color: #FFF',       // 反转
    
    // 前景色
    30: 'color: #000',    // 黑
    31: 'color: #A00',    // 红
    32: 'color: #0A0',    // 绿
    33: 'color: #A50',    // 黄
    34: 'color: #00A',    // 蓝
    35: 'color: #A0A',    // 紫
    36: 'color: #0AA',    // 青
    37: 'color: #AAA',    // 白
    
    // 亮色前景
    90: 'color: #555',    // 亮黑（灰）
    91: 'color: #F55',    // 亮红
    92: 'color: #5F5',    // 亮绿
    93: 'color: #FF5',    // 亮黄
    94: 'color: #55F',    // 亮蓝
    95: 'color: #F5F',    // 亮紫
    96: 'color: #5FF',    // 亮青
    97: 'color: #FFF',    // 亮白
    
    // 背景色
    40: 'background-color: #000',    // 黑
    41: 'background-color: #A00',    // 红
    42: 'background-color: #0A0',    // 绿
    43: 'background-color: #A50',    // 黄
    44: 'background-color: #00A',    // 蓝
    45: 'background-color: #A0A',    // 紫
    46: 'background-color: #0AA',    // 青
    47: 'background-color: #AAA',    // 白
    
    // 亮色背景
    100: 'background-color: #555',   // 亮黑（灰）
    101: 'background-color: #F55',   // 亮红
    102: 'background-color: #5F5',   // 亮绿
    103: 'background-color: #FF5',   // 亮黄
    104: 'background-color: #55F',   // 亮蓝
    105: 'background-color: #F5F',   // 亮紫
    106: 'background-color: #5FF',   // 亮青
    107: 'background-color: #FFF'    // 亮白
  };
  
  /**
   * 将ANSI转义序列转换为HTML
   * @param {string} text 包含ANSI转义序列的文本
   * @return {string} 转换后的HTML
   */
  export function ansiToHtml(text) {
    if (!text) return '';
    
    // 替换常见的控制字符
    text = text.replace(/\r\n/g, '\n')             // Windows换行符转为\n
              .replace(/\r/g, '\n')                // 单独的\r也转为\n
              .replace(/\t/g, '    ');             // 制表符转为4个空格
    
    // 匹配ANSI转义序列的正则表达式
    const ansiPattern = /\x1b\[((?:\d{1,3};)*\d{1,3})m/g;
    
    // 当前激活的样式
    let activeStyles = [];
    
    // 分割文本和转义序列
    const parts = [];
    let lastIndex = 0;
    let match;
    
    while ((match = ansiPattern.exec(text)) !== null) {
      // 添加转义序列前的文本
      if (match.index > lastIndex) {
        parts.push({
          text: text.substring(lastIndex, match.index),
          styles: [...activeStyles]
        });
      }
      
      // 处理转义序列
      const ansiCodes = match[1].split(';').map(Number);
      
      // 处理特殊情况: \x1b[0m 重置所有样式
      if (ansiCodes.includes(0)) {
        activeStyles = [];
      } else {
        // 添加新样式
        for (const code of ansiCodes) {
          if (ANSI_COLORS[code]) {
            activeStyles.push(code);
          }
        }
      }
      
      lastIndex = match.index + match[0].length;
    }
    
    // 添加最后一部分文本
    if (lastIndex < text.length) {
      parts.push({
        text: text.substring(lastIndex),
        styles: [...activeStyles]
      });
    }
    
    // 转换为HTML
    let html = '';
    
    for (const part of parts) {
      if (part.text) {
        if (part.styles.length > 0) {
          const styleStr = part.styles
            .map(code => ANSI_COLORS[code])
            .filter(Boolean)
            .join('; ');
            
          html += `<span style="${styleStr}">${escapeHtml(part.text)}</span>`;
        } else {
          html += escapeHtml(part.text);
        }
      }
    }
    
    // 替换换行符为<br>
    html = html.replace(/\n/g, '<br>');
    
    return html;
  }
  
  /**
   * 转义HTML特殊字符
   * @param {string} text 需要转义的文本
   * @return {string} 转义后的文本
   */
  function escapeHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
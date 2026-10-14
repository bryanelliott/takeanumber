/* Focused DOM checks, not a WCAG certification or replacement for assistive technology. */
(() => {
  const visible = node => node.getClientRects().length && getComputedStyle(node).visibility !== "hidden"
    && !node.closest('.screen-reader-only, [hidden]');
  const errors = [];
  const ids = [...document.querySelectorAll('[id]')].map(node => node.id);
  if (new Set(ids).size !== ids.length) errors.push('Duplicate IDs');
  if (!document.documentElement.lang) errors.push('Missing document language');
  if (document.querySelectorAll('main').length !== 1) errors.push('Main landmark count');
  if (document.querySelectorAll('h1').length !== 1) errors.push('H1 count');
  for (const node of document.querySelectorAll('[aria-labelledby], [aria-describedby], [aria-controls]')) {
    for (const name of ['aria-labelledby', 'aria-describedby', 'aria-controls']) {
      for (const id of (node.getAttribute(name) || '').split(/\s+/).filter(Boolean)) {
        if (!document.getElementById(id)) errors.push(`Missing ${name} target ${id}`);
      }
    }
  }
  for (const node of document.querySelectorAll('input:not([type=hidden]), select, textarea, button')) {
    const name = node.getAttribute('aria-label') || node.getAttribute('aria-labelledby')
      || node.labels?.length || (node.tagName === 'BUTTON' && node.textContent.trim())
      || (node.type === 'submit' && node.value);
    if (!name) errors.push(`Unnamed control ${node.id || node.tagName}`);
    if (visible(node) && node.matches('button, input[type=submit]')
        && node.getBoundingClientRect().height < 44) errors.push(`Small button ${node.id}`);
  }
  for (const img of document.images) {
    if (!img.hasAttribute('alt')) errors.push('Missing image alternative');
    if (visible(img) && !img.naturalWidth) errors.push('Image failed to load');
  }
  const luminance = rgb => rgb.slice(0, 3).map(value => {
    const channel = value / 255;
    return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
  }).reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0);
  const rgba = color => (color.match(/[\d.]+/g) || []).map(Number);
  const contrast = (a, b) => (Math.max(luminance(a), luminance(b)) + .05)
    / (Math.min(luminance(a), luminance(b)) + .05);
  const textRatios = [];
  for (const node of document.querySelectorAll('p, a, button, label, span, h1, h2, h3, summary')) {
    if (!visible(node) || node.disabled || ![...node.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    const style = getComputedStyle(node);
    if (Number(style.opacity) !== 1) continue;
    let background = [255, 255, 255], ancestor = node;
    while (ancestor) {
      const color = rgba(getComputedStyle(ancestor).backgroundColor);
      if (color.length === 3 || color[3] === 1) { background = color; break; }
      ancestor = ancestor.parentElement;
    }
    const foreground = rgba(style.color);
    if (foreground.length < 3) continue;
    const ratio = contrast(foreground, background);
    const large = parseFloat(style.fontSize) >= 24
      || (parseFloat(style.fontSize) >= 18.67 && Number(style.fontWeight) >= 700);
    textRatios.push(ratio);
    if (ratio + .01 < (large ? 3 : 4.5)) errors.push(`Text contrast ${node.className}: ${ratio.toFixed(2)}`);
  }
  const qr = document.querySelector('.qr');
  const serving = document.querySelector('.queue-status--serving');
  const next = document.querySelector('.queue-status--next');
  const rect = node => node && ({width: node.getBoundingClientRect().width,
    height: node.getBoundingClientRect().height, bottom: node.getBoundingClientRect().bottom,
    left: node.getBoundingClientRect().left, top: node.getBoundingClientRect().top});
  return {errors, width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth,
    minTextContrast: Math.min(...textRatios), qr: rect(qr), serving: rect(serving), next: rect(next),
    connection: rect(document.querySelector('#live-status')),
    cls: window.__qaCls || 0,
    navigationMs: performance.getEntriesByType('navigation')[0]?.duration,
    resources: performance.getEntriesByType('resource').map(r => ({path: new URL(r.name).pathname,
      bytes: r.encodedBodySize, durationMs: r.duration}))};
})()

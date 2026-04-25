#!/usr/bin/env python3
"""
Hermes Site Builder — Single Source of Truth for Navigation
Generates all HTML pages from templates + data.
Usage: python3 build.py
"""
import json, os, re

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(SITE_DIR, 'src')
DATA_DIR = os.path.join(SRC_DIR, 'data')
TMPL_DIR = os.path.join(SRC_DIR, 'templates')
CONTENT_DIR = os.path.join(SRC_DIR, 'content')

# Load base template
with open(os.path.join(TMPL_DIR, 'base.html'), 'r') as f:
    BASE_TMPL = f.read()

# Load nav data
with open(os.path.join(DATA_DIR, 'nav.json'), 'r') as f:
    NAV_DATA = json.load(f)

# Icons (simplified SVG paths)
ICONS = {
    'home': '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>'
}

THEME_TOGGLE_HTML = '''<button id="theme-toggle" aria-label="Theme wechseln" title="Theme wechseln" style="background:none;border:none;cursor:pointer;color:var(--c-text-muted);padding:var(--s-2);border-radius:var(--r-sm);display:flex;align-items:center;margin-left:auto;transition:color var(--t)">
    <svg id="icon-sun" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="display:none"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>
    <svg id="icon-moon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
  </button>'''

THEME_SCRIPT = '''<script>
(function(){
  var btn = document.getElementById('theme-toggle');
  var iconSun = document.getElementById('icon-sun');
  var iconMoon = document.getElementById('icon-moon');
  function setTheme(t){
    document.documentElement.className = t;
    localStorage.setItem('theme', t);
    if(iconSun) iconSun.style.display = t === 'dark' ? 'none' : 'block';
    if(iconMoon) iconMoon.style.display = t === 'dark' ? 'block' : 'none';
  }
  var current = localStorage.getItem('theme') || 'dark';
  setTheme(current);
  if(btn) btn.addEventListener('click', function(){
    current = current === 'dark' ? 'light' : 'dark';
    setTheme(current);
  });
})();
</script>'''

def build_nav(current_path):
    """Build navigation HTML with active link highlighted."""
    # Normalize current path
    current = current_path.replace('.html', '')
    if current.endswith('/index'):
        current = current[:-5] or '/'
    if current == 'index':
        current = '/'

    parts = ['<nav class="nav" aria-label="Hauptnavigation">']
    for link in NAV_DATA['links']:
        href = link['href']
        label = link['label']
        icon = link.get('icon')

        # Determine active state
        is_active = False
        if href == '/' and current == '/':
            is_active = True
        elif href != '/' and current.startswith(href):
            is_active = True

        attrs = ' aria-current="page"' if is_active else ''

        if icon and icon in ICONS:
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{ICONS[icon]}</svg>'
            parts.append(f'  <a href="{href}"{attrs}>{svg}\n    {label}\n  </a>')
        else:
            parts.append(f'  <a href="{href}"{attrs}>{label}</a>')

    # Add separator after first link (Dashboard)
    if len(parts) > 1:
        parts.insert(2, '  <span class="sep" aria-hidden="true">\u00b7</span>')

    parts.append(THEME_TOGGLE_HTML)
    parts.append('</nav>')
    parts.append(THEME_SCRIPT)
    return '\n'.join(parts)


def parse_content_file(path):
    """Parse a content fragment file into title, extra_head, body."""
    with open(path, 'r') as f:
        raw = f.read()

    # Parse title
    title_match = re.search(r'<!--TITLE:(.*?)-->', raw)
    title = title_match.group(1).strip() if title_match else 'Hermes'

    # Parse head section
    head_match = re.search(r'<!--HEAD-->(.*?)<!--/HEAD-->', raw, re.DOTALL)
    extra_head = head_match.group(1).strip() if head_match else ''

    # Parse body section
    body_match = re.search(r'<!--BODY-->(.*?)<!--/BODY-->', raw, re.DOTALL)
    body = body_match.group(1).strip() if body_match else raw

    # Inline JSON data if <!--DATA:/path/to.json--> is present
    data_match = re.search(r'<!--DATA:(.+?)-->', body)
    if data_match:
        data_path = data_match.group(1).strip()
        # Resolve relative to site root
        full_data_path = os.path.join(SITE_DIR, data_path.lstrip('/'))
        if os.path.exists(full_data_path):
            with open(full_data_path, 'r') as df:
                data_content = df.read()
            # Validate JSON
            json.loads(data_content)
            # Insert before the first <script> tag or at the end of body
            data_script = '<script>window.__DATA__ = ' + data_content + ';</script>\n'
            # Remove the DATA comment
            body = body.replace(data_match.group(0), '')
            # Find first <script> and insert before it
            script_match = re.search(r'<script', body)
            if script_match:
                pos = script_match.start()
                body = body[:pos] + data_script + body[pos:]
            else:
                body = body + '\n' + data_script
        else:
            print(f'  WARN: Data file not found: {full_data_path}')

    return title, extra_head, body


def build_page(content_path, out_path):
    """Render a single page."""
    rel = os.path.relpath(content_path, CONTENT_DIR)
    # Determine web path for active link calculation
    web_path = '/' + rel.replace('.html', '')
    if web_path.endswith('/index'):
        web_path = web_path[:-5] or '/'
    if web_path == '/index':
        web_path = '/'

    title, extra_head, body = parse_content_file(content_path)
    nav_html = build_nav(web_path)

    html = BASE_TMPL \
        .replace('{{title}}', title) \
        .replace('{{extra_head}}', extra_head) \
        .replace('{{nav}}', nav_html) \
        .replace('{{content}}', body)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(html)
    print(f'  Built {out_path} (path={web_path})')


def main():
    print('Building Hermes site...')

    # Build all content files
    for root, dirs, files in os.walk(CONTENT_DIR):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            content_path = os.path.join(root, fname)
            rel = os.path.relpath(content_path, CONTENT_DIR)
            out_path = os.path.join(SITE_DIR, rel)
            build_page(content_path, out_path)

    print('Done.')

if __name__ == '__main__':
    main()

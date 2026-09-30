"""Assemble l'interface en un seul fichier servi par le service web.

Usage : python web/build.py   (écrit src/car_sourcing/web/static/index.html)
"""

from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent / "src" / "car_sourcing" / "web" / "static" / "index.html"
FILES = ["domain.js", "ui-core.js", "ui-feed.js", "ui-pages.js", "ui-settings.js"]

js = '"use strict";\n' + "\n".join((HERE / f).read_text(encoding="utf-8") for f in FILES)
js += "\n['opps','calc','list','chart','sliders'].forEach(k => { const el = document.getElementById('ico-' + k); if (el) el.outerHTML = ICON[k]; });\n"
html = (HERE / "shell.html").read_text(encoding="utf-8")
html = html.replace("/*CSS*/", (HERE / "styles.css").read_text(encoding="utf-8")).replace("/*JS*/", js)
OUT.write_text(html, encoding="utf-8")
print(f"{OUT} ({len(html) // 1024} ko)")

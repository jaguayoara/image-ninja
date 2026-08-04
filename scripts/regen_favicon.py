"""
DEPRECADO: ahora el branding se regenera con models/_make_logos.py
a partir del logo real (assets/logo.png).

Si actualizas el logo:
  1. Reemplaza assets/logo.png con la nueva imagen
  2. Ejecuta:  python models/_make_logos.py
  3. Listo — genera:
     - assets/logo-readme.png  (1600px, liviano para README)
     - assets/logo-square.png  (1024x1024, para og-image)
     - static/img/ninja-mascot.png  (512px, transparente, para topbar)
     - static/img/favicon.png  (32x32)
     - static/img/apple-touch-icon.png  (180x180)
     - static/img/og-image.png  (1200x630 social card)
     - static/favicon.ico  (copia de favicon.png)
     - static/banner.png  (copia de logo-readme.png)
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    script = BASE / "scripts" / "make_logos.py"
    if not script.exists():
        print(f"ERROR: {script} no existe")
        sys.exit(1)
    print(f"Ejecutando {script.relative_to(BASE)} ...")
    sys.exit(subprocess.call([sys.executable, str(script)], cwd=str(BASE)))

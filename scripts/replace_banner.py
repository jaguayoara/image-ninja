import shutil
from pathlib import Path
shutil.copy("assets/logo-readme.png", "static/banner.png")
print(f"banner.png: {Path('static/banner.png').stat().st_size // 1024} KB")
shutil.copy("static/img/favicon.png", "static/favicon.ico")
print(f"favicon.ico: {Path('static/favicon.ico').stat().st_size} B")

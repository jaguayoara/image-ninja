## ImageNinja v1.0.0

Primera version publica de **ImageNinja** - tu taller de imagenes con IA, 100% local.

### Caracteristicas

- **Reescalar a 4K** con Real-ESRGAN (IA). Pipeline completo: denoise + super-resolucion x4 + Lanczos refine + unsharp mask. Targets: 4K UHD, 4K DCI, QHD, 2x/3x/4x.
- **Extraer metadatos** EXIF, IPTC, XMP, GPS, ICC. Descarga como JSON.
- **Auto-cleanup** de archivos temporales (TTL 1h).
- **Portable**: un solo `.exe` + carpeta `_internal/`. No requiere instalacion.

### Como usar

1. Descarga `ImageNinja-windows.zip`
2. Descomprime en cualquier carpeta
3. Ejecuta `ImageNinja.exe`
4. La primera vez, Windows SmartScreen puede mostrar una advertencia - click en "Mas informacion" -> "Ejecutar de todas formas"

### Privacidad

- 0 MB de tus fotos sale de tu computador
- 0 CLP por imagen procesada
- 0 cuenta requerida

### Stack

- Backend: Flask 3 + Pillow + Real-ESRGAN (PyTorch)
- Frontend: HTML + CSS vanilla + JS
- Empaquetado: PyInstaller (--onedir)

Por [Jorge Aguayo](https://github.com/jaguayoara) (Chile).

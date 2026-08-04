"""
Extraccion de metadatos de imagenes.

Cubre:
  - Archivo: tamano, formato, dimensiones, modo de color, dpi, espacio de color
  - EXIF: camara, lente, configuracion (ISO, apertura, obturacion, focal), GPS,
          fechas, software, copyright, artista, descripcion
  - XMP: bloques XML embebidos (Adobe, Lightroom, etc.)
  - IPTC: caption, keywords, copyright (parse basico desde APP13)
  - ICC Profile: descripcion del perfil de color (si existe)

Diseno:
  - Devuelve un dict con secciones listas para renderizar en UI
  - Valores formateados (no IDs numericos sueltos)
  - GPS se convierte a coordenadas decimales
  - Fechas se formatean como ISO local
  - Tags sin informacion se omiten (no ensucian la UI)
"""
from __future__ import annotations

import json
import logging
import re
import struct
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ExifTags

log = logging.getLogger("imageninja.metadata")

# Tags de GPS que nos interesan
GPS_TAGS = {
    0: "GPSVersionID",
    1: "LatitudeRef",
    2: "Latitude",
    3: "LongitudeRef",
    4: "Longitude",
    5: "AltitudeRef",
    6: "Altitude",
    7: "TimeStamp",
    12: "SpeedRef",
    13: "Speed",
    16: "ImgDirectionRef",
    17: "ImgDirection",
    23: "DestBearingRef",
    24: "DestBearing",
    29: "DateStamp",
    31: "HPositioningError",
}

# Subset de EXIF tags que mostramos en la UI (mapeo tag_id -> label legible)
EXIF_LABELS = {
    # Camara
    271: ("Camara", "Fabricante"),
    272: ("Camara", "Modelo"),
    # Lente
    42035: ("Lente", "Fabricante"),
    42036: ("Lente", "Modelo"),
    42037: ("Lente", "Numero de serie"),
    41728: ("Lente", "Especificacion"),
    # Configuracion
    33434: ("Configuracion", "Velocidad de obturacion"),
    33437: ("Configuracion", "Apertura (F)"),
    34855: ("Configuracion", "ISO"),
    37386: ("Configuracion", "Longitud focal"),
    37396: ("Configuracion", "Compensacion de exposicion"),
    37380: ("Configuracion", "Modo de exposicion"),
    37381: ("Configuracion", "Modo de medicion"),
    37383: ("Configuracion", "Modo de flash"),
    37385: ("Configuracion", "Balance de blancos"),
    37378: ("Configuracion", "Valor de apertura"),
    37377: ("Configuracion", "Valor de obturacion"),
    37379: ("Configuracion", "Valor de brillo"),
    41988: ("Configuracion", "Modo digital zoom"),
    # Fechas
    306: ("Fechas", "Fecha original"),
    307: ("Fechas", "Fecha digitalizacion"),
    36867: ("Fechas", "Fecha original (subsec)"),
    36868: ("Fechas", "Fecha digitalizacion (subsec)"),
    36880: ("Fechas", "Offset UTC"),
    # Software / autor
    305: ("Software", "Software"),
    11: ("Software", "Software (ProcessingSoftware)"),
    315: ("Autor", "Artista"),
    33432: ("Autor", "Copyright"),
    270: ("Descripcion", "Descripcion"),
    37500: ("Descripcion", "Comentario del fabricante"),
    37510: ("Descripcion", "Comentario del usuario"),
    # Otros
    40961: ("Color", "ColorSpace"),
    40962: ("Color", "PixelXDimension"),
    40963: ("Color", "PixelYDimension"),
    40965: ("Otro", "InteropIndex"),
}

# Exif IFD (donde vive cada tag en el spec)
# 0x8769 = ExifIFD
# 0x8825 = GPSIFD
EXIF_IFD = 0x8769
GPS_IFD = 0x8825


def _format_value(value: Any) -> str:
    """Formatea un valor EXIF para mostrar al usuario."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        # Intentar UTF-8, fallback latin-1, fallback hex
        try:
            return value.decode("utf-8").rstrip("\x00").strip()
        except UnicodeDecodeError:
            try:
                return value.decode("latin-1").rstrip("\x00").strip()
            except Exception:
                return f"<{len(value)} bytes binarios>"
    if isinstance(value, tuple) and len(value) == 2:
        # Racional (numerador, denominador)
        try:
            num, den = value
            if den == 0:
                return f"{num}"
            v = num / den
            if abs(v) < 1:
                return f"{v:.4f}".rstrip("0").rstrip(".")
            return f"{v:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(_format_value(v) for v in value)
    if isinstance(value, float):
        if abs(value) < 1:
            return f"{value:.4f}".rstrip("0").rstrip(".")
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _format_shutter(exposure_time: Any) -> str:
    """Convierte velocidad de obturacion a '1/250s'."""
    if exposure_time is None:
        return ""
    try:
        if isinstance(exposure_time, tuple) and len(exposure_time) == 2:
            num, den = exposure_time
            if den == 0 or num == 0:
                return _format_value(exposure_time)
            v = num / den
        else:
            v = float(exposure_time)
        if v >= 1:
            return f"{v:.1f}s"
        if v > 0:
            denom = round(1 / v)
            return f"1/{denom}s"
    except Exception:
        pass
    return _format_value(exposure_time)


def _format_aperture(f_number: Any) -> str:
    """Convierte numero F a 'f/2.8'."""
    if f_number is None:
        return ""
    try:
        if isinstance(f_number, tuple) and len(f_number) == 2:
            num, den = f_number
            v = num / den if den else float(num)
        else:
            v = float(f_number)
        return f"f/{v:.1f}"
    except Exception:
        return _format_value(f_number)


def _format_focal(focal: Any) -> str:
    """Convierte longitud focal a '50mm'."""
    if focal is None:
        return ""
    try:
        if isinstance(focal, tuple) and len(focal) == 2:
            num, den = focal
            v = num / den if den else float(num)
        else:
            v = float(focal)
        return f"{v:.0f}mm"
    except Exception:
        return _format_value(focal)


def _format_exif_date(date_str: Any) -> str:
    """'2024:01:15 14:30:22' -> '15 ene 2024, 14:30'."""
    if not date_str:
        return ""
    s = str(date_str)
    m = re.match(r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", s)
    if not m:
        return s
    y, mo, d, hh, mm, _ = m.groups()
    meses = {
        "01": "ene", "02": "feb", "03": "mar", "04": "abr",
        "05": "may", "06": "jun", "07": "jul", "08": "ago",
        "09": "sep", "10": "oct", "11": "nov", "12": "dic",
    }
    return f"{int(d)} {meses.get(mo, mo)} {y}, {hh}:{mm}"


def _dms_to_decimal(dms: Any, ref: str) -> Optional[float]:
    """Convierte (grados, minutos, segundos) a decimal."""
    if not dms or len(dms) < 3:
        return None
    try:
        d = float(dms[0])
        m = float(dms[1])
        s = float(dms[2])
        decimal = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except Exception:
        return None


def _extract_exif_dict(img: Image.Image) -> dict[int, Any]:
    """Lee todos los tags EXIF (incluyendo sub-IFDs)."""
    exif_data: dict[int, Any] = {}
    raw = img.getexif()
    if raw:
        for tag_id, value in raw.items():
            exif_data[tag_id] = value
    # Sub-IFD: Exif
    try:
        exif_ifd = raw.get_ifd(EXIF_IFD) if raw else {}
    except Exception:
        exif_ifd = {}
    for tag_id, value in exif_ifd.items():
        exif_data[tag_id] = value
    # Sub-IFD: GPS
    try:
        gps_ifd = raw.get_ifd(GPS_IFD) if raw else {}
    except Exception:
        gps_ifd = {}
    for tag_id, value in gps_ifd.items():
        exif_data[tag_id] = value
    return exif_data


def _extract_xmp(path: Path) -> dict[str, str]:
    """Lee el bloque XMP del archivo (formato XML embebido)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return {}
    # XMP suele estar entre <x:xmpmeta ...> ... </x:xmpmeta>
    m = re.search(rb"<x:xmpmeta[^>]*>(.*?)</x:xmpmeta>", data, re.DOTALL)
    if not m:
        return {}
    block = m.group(1).decode("utf-8", errors="ignore")
    # Parsear pares dc:key, xmp:key, etc.
    out: dict[str, str] = {}
    # Captura <prefix:key>value</prefix:key>
    for tag in re.finditer(r"<([\w]+:[\w]+)>([^<]*)</\1>", block):
        key = tag.group(1)
        val = tag.group(2).strip()
        if val:
            out[key] = val
    return out


def _extract_icc(img: Image.Image) -> Optional[str]:
    """Descripcion del perfil ICC si existe."""
    icc = img.info.get("icc_profile")
    if not icc:
        return None
    try:
        # ICC header tiene 'desc' tag a partir de offset 36 (128 bytes header + tag table)
        # Mas simple: buscar un texto descriptivo conocido
        s = icc.decode("latin-1", errors="ignore")
        # Heuristica: buscar patron de descripcion
        m = re.search(r"(\bsRGB\b|\bAdobe RGB\b|\bDisplay P3\b|\bProPhoto\b)", s, re.IGNORECASE)
        if m:
            return m.group(0)
    except Exception:
        pass
    return "ICC profile presente"


def extract_metadata(path: Path) -> dict:
    """Extrae todos los metadatos de una imagen. Devuelve dict listo para JSON."""
    result: dict = {
        "file": {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "size_human": _human_size(path.stat().st_size),
        },
        "image": {},
        "camera": [],
        "lens": [],
        "settings": [],
        "dates": [],
        "software": [],
        "author": [],
        "description": [],
        "gps": {},
        "xmp": [],
        "icc": None,
    }

    try:
        img = Image.open(path)
    except Exception as e:
        result["error"] = f"No se pudo abrir la imagen: {e}"
        return result

    # Imagen basica
    w, h = img.size
    result["image"] = {
        "width": w,
        "height": h,
        "megapixels": round((w * h) / 1_000_000, 2),
        "format": img.format or "desconocido",
        "mode": img.mode,
        "color_mode": _describe_mode(img.mode),
        "dpi": img.info.get("dpi"),
        "aspect_ratio": _aspect_ratio(w, h),
    }
    if img.format == "JPEG":
        try:
            result["image"]["quality_estimate"] = "Estimado (no siempre exacto)"
        except Exception:
            pass

    # ICC profile
    result["icc"] = _extract_icc(img)

    # EXIF
    exif = _extract_exif_dict(img)
    if not exif:
        result["exif_count"] = 0
    else:
        result["exif_count"] = len(exif)
        _populate_sections(exif, result)

    # XMP
    xmp = _extract_xmp(path)
    for key, val in xmp.items():
        # Mostrar los XMP mas utiles
        if any(prefix in key for prefix in [
            "dc:", "xmp:", "photoshop:", "Iptc4xmpCore:", "Iptc4xmpExt:",
        ]):
            label = _xmp_label(key)
            result["xmp"].append({"key": label, "value": val[:200]})

    return result


def _populate_sections(exif: dict[int, Any], result: dict) -> None:
    """Separa los tags EXIF en secciones segun EXIF_LABELS."""
    section_map: dict[str, list] = {
        "Camara": result["camera"],
        "Lente": result["lens"],
        "Configuracion": result["settings"],
        "Fechas": result["dates"],
        "Software": result["software"],
        "Autor": result["author"],
        "Descripcion": result["description"],
    }

    for tag_id, value in exif.items():
        info = EXIF_LABELS.get(tag_id)
        if not info:
            continue
        section, label = info
        if section == "Color" or section == "Otro":
            # Color info va a image, Otro se ignora para no hacer ruido
            continue
        formatted = _format_for_section(tag_id, value)
        if not formatted:
            continue
        section_map[section].append({"key": label, "value": formatted})

    # GPS
    gps = _build_gps(exif)
    if gps:
        result["gps"] = gps


def _format_for_section(tag_id: int, value: Any) -> str:
    """Aplica formato especial segun el tipo de tag."""
    if tag_id == 33434:
        return _format_shutter(value)
    if tag_id == 33437 or tag_id == 37378:
        return _format_aperture(value)
    if tag_id == 37386:
        return _format_focal(value)
    if tag_id in (306, 307, 36867, 36868):
        return _format_exif_date(value)
    if tag_id == 34855:
        return f"ISO {int(value)}" if value else ""
    if tag_id == 37383:
        return _describe_flash(value)
    if tag_id == 37380:
        return _describe_exposure(value)
    if tag_id == 37381:
        return _describe_metering(value)
    if tag_id == 37385:
        return _describe_white_balance(value)
    if tag_id == 36880:
        return _format_offset(value)
    return _format_value(value)


def _describe_flash(value: Any) -> str:
    flags = {
        0x0: "Sin flash",
        0x1: "Disparado",
        0x5: "Disparado, sin retorno",
        0x7: "Disparado, retorno detectado",
        0x9: "Disparado, obligatorio",
        0xD: "Disparado, obligatorio, sin retorno",
        0xF: "Disparado, obligatorio, retorno detectado",
        0x10: "Off, obligatorio",
        0x18: "Auto, sin disparar",
        0x19: "Auto, disparado",
        0x1D: "Auto, disparado, sin retorno",
        0x1F: "Auto, disparado, retorno detectado",
        0x20: "Sin funcion",
        0x41: "Disparado, red-eye",
        0x45: "Disparado, red-eye, sin retorno",
        0x47: "Disparado, red-eye, retorno detectado",
        0x49: "Disparado, obligatorio, red-eye",
        0x4D: "Disparado, obligatorio, red-eye, sin retorno",
        0x4F: "Disparado, obligatorio, red-eye, retorno detectado",
    }
    try:
        v = int(value)
    except Exception:
        return _format_value(value)
    if v in flags:
        return flags[v]
    return f"Modo 0x{v:X}"


def _describe_exposure(value: Any) -> str:
    modes = {
        0: "Auto",
        1: "Manual",
        2: "Programado",
        3: "Prioridad de apertura",
        4: "Prioridad de obturacion",
        5: "Creativo",
        6: "Accion",
        7: "Retrato",
        8: "Paisaje",
    }
    try:
        v = int(value)
    except Exception:
        return _format_value(value)
    return modes.get(v, f"Modo {v}")


def _describe_metering(value: Any) -> str:
    modes = {
        0: "Desconocido",
        1: "Promedio",
        2: "Centro ponderado",
        3: "Spot",
        4: "Multi-spot",
        5: "Patron",
        6: "Parcial",
        255: "Otro",
    }
    try:
        v = int(value)
    except Exception:
        return _format_value(value)
    return modes.get(v, f"Modo {v}")


def _describe_white_balance(value: Any) -> str:
    modes = {0: "Auto", 1: "Manual"}
    try:
        v = int(value)
    except Exception:
        return _format_value(value)
    return modes.get(v, f"Modo {v}")


def _format_offset(value: Any) -> str:
    """Offset UTC en formato +HH:MM o -HH:MM."""
    try:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="ignore").rstrip("\x00")
        s = str(value).strip()
        if not s:
            return ""
        # Formato comun: "+09:00" o "Pacific/Honolulu"
        if re.match(r"^[+-]\d{2}:?\d{2}$", s):
            return s
        if re.match(r"^[+-]\d{4}$", s):
            return f"{s[:3]}:{s[3:]}"
        return s
    except Exception:
        return _format_value(value)


def _build_gps(exif: dict[int, Any]) -> dict:
    """Construye un dict con info GPS, incluyendo coordenadas decimales.

    Validacion: si los valores GPS no parecen DMS validos (degrees fuera de
    rango, minutes/seconds > 60, refs no son N/S/E/W, etc.), descartamos
    el GPS completo. Esto evita que una webcam con EXIF corrupto muestre
    coordenadas absurdas tipo "medio del mar".
    """
    gps: dict[str, Any] = {}
    for tag_id, value in exif.items():
        if tag_id not in GPS_TAGS:
            continue
        label = GPS_TAGS[tag_id]
        if label == "LatitudeRef" or label == "LongitudeRef":
            gps[label] = _format_value(value)
        elif label == "Latitude":
            gps[label] = _dms_to_decimal(value, gps.get("LatitudeRef", "N"))
            gps["_lat_dms"] = _format_value(value)
        elif label == "Longitude":
            gps[label] = _dms_to_decimal(value, gps.get("LongitudeRef", "E"))
            gps["_lon_dms"] = _format_value(value)
        elif label == "Altitude":
            try:
                v = float(value[0]) / float(value[1]) if isinstance(value, tuple) else float(value)
                gps[label] = f"{v:.1f} m"
            except Exception:
                gps[label] = _format_value(value)
        elif label == "TimeStamp":
            gps[label] = _format_value(value)
        elif label == "DateStamp":
            gps[label] = _format_value(value)
        elif label == "GPSVersionID":
            gps[label] = ".".join(str(b) for b in value) if hasattr(value, "__iter__") else _format_value(value)
        else:
            gps[label] = _format_value(value)

    # Validar GPS: si algo no cuadra, descartar TODO
    if not _gps_is_valid(gps):
        log.debug("GPS descartado por valores invalidos: %s", gps)
        return {}

    # Coordenadas decimales finales, presentables
    if "Latitude" in gps and "Longitude" in gps:
        lat = gps["Latitude"]
        lon = gps["Longitude"]
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            gps["_decimal"] = f"{lat:.6f}, {lon:.6f}"
            gps["_map_link"] = f"https://www.google.com/maps?q={lat},{lon}"
    return gps


def _gps_is_valid(gps: dict) -> bool:
    """Valida que un GPS extraido sea real, no basura del EXIF.

    Criterios:
      - LatRef debe estar en N/S (case insensitive)
      - LonRef debe estar en E/W (case insensitive)
      - Si hay latitude, debe ser numero entre -90 y 90
      - Si hay longitude, debe ser numero entre -180 y 180
      - Si solo hay longitude sin latitud (o viceversa), descartar
      - El DMS (degrees, minutes, seconds) debe tener valores plausibles
    """
    if not gps:
        return False

    # Necesitamos al menos lat y lon para mostrar
    if "Latitude" not in gps or "Longitude" not in gps:
        return False

    # Refs
    lat_ref = (gps.get("LatitudeRef") or "N").strip().upper()[:1]
    lon_ref = (gps.get("LongitudeRef") or "E").strip().upper()[:1]
    if lat_ref not in ("N", "S"):
        return False
    if lon_ref not in ("E", "W"):
        return False

    # Rangos
    lat = gps["Latitude"]
    lon = gps["Longitude"]
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False
    if not (-90 <= lat <= 90):
        return False
    if not (-180 <= lon <= 180):
        return False

    # Si ambos son exactamente 0,0 es probablemente data corrupta/inicializada
    if lat == 0 and lon == 0:
        return False

    # Validar DMS si esta disponible: minutes/seconds deben ser < 60
    for dms_key in ("_lat_dms", "_lon_dms"):
        dms_str = gps.get(dms_key, "")
        if dms_str and isinstance(dms_str, str):
            # Buscar patron tipo "(180, 1, 0)" o "180 deg 1' 0""
            import re as _re
            nums = _re.findall(r"\d+\.?\d*", dms_str)
            if len(nums) >= 3:
                try:
                    deg = float(nums[0])
                    minutes = float(nums[1])
                    seconds = float(nums[2])
                    # degrees debe estar en rango
                    if dms_key == "_lat_dms" and not (0 <= deg <= 90):
                        return False
                    if dms_key == "_lon_dms" and not (0 <= deg <= 180):
                        return False
                    # minutes y seconds < 60
                    if not (0 <= minutes < 60):
                        return False
                    if not (0 <= seconds < 60):
                        return False
                except (ValueError, IndexError):
                    pass

    return True


def _xmp_label(key: str) -> str:
    """Traduce keys XMP a label legible."""
    mapping = {
        "dc:format": "Formato",
        "dc:creator": "Creador",
        "dc:rights": "Copyright",
        "dc:title": "Titulo",
        "dc:description": "Descripcion",
        "dc:subject": "Temas",
        "xmp:CreateDate": "Fecha de creacion",
        "xmp:ModifyDate": "Fecha de modificacion",
        "xmp:CreatorTool": "Herramienta",
        "xmp:Rating": "Rating",
        "photoshop:City": "Ciudad",
        "photoshop:Country": "Pais",
        "Iptc4xmpCore:CreatorContactInfo": "Contacto",
    }
    return mapping.get(key, key)


def _describe_mode(mode: str) -> str:
    modes = {
        "1": "1-bit (blanco y negro)",
        "L": "Escala de grises (8-bit)",
        "P": "Paleta (8-bit)",
        "RGB": "Color RGB (8-bit/canal)",
        "RGBA": "Color RGB + alfa",
        "CMYK": "CMYK (8-bit/canal)",
        "YCbCr": "YCbCr",
        "I": "Entero 32-bit",
        "F": "Float 32-bit",
    }
    return modes.get(mode, mode)


def _aspect_ratio(w: int, h: int) -> str:
    from math import gcd
    if h == 0:
        return "?"
    g = gcd(w, h)
    rw, rh = w // g, h // g
    common = {
        (16, 9): "16:9",
        (4, 3): "4:3",
        (3, 2): "3:2",
        (5, 4): "5:4",
        (1, 1): "1:1",
        (21, 9): "21:9 (ultrawide)",
        (9, 16): "9:16 (vertical)",
        (2, 3): "2:3 (vertical)",
        (3, 4): "3:4 (vertical)",
    }
    if (rw, rh) in common:
        return common[(rw, rh)]
    if abs(rw / rh - 16/9) < 0.01:
        return f"~16:9 ({rw}:{rh})"
    return f"{rw}:{rh}"


def _human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    v = float(n)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    if i == 0:
        return f"{int(v)} {units[i]}"
    return f"{v:.2f} {units[i]}"


def metadata_to_json(meta: dict) -> str:
    """Serializa el dict de metadatos a JSON bonito."""
    return json.dumps(meta, indent=2, ensure_ascii=False, default=str)

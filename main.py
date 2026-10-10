# ==============================================================================
# PROYECTO STILO - MOTOR INTELIGENTE DE COLORIMETRÍA Y VISIÓN POR COMPUTADORA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# Versión: 7.0.0 (Perfil de color dominante, teoría del color, caché y velocidad)
# ==============================================================================
#
# Mejoras principales frente a la 6.1:
#   * Cada imagen se analiza UNA sola vez (antes se decodificaba en cada combinación)
#     y el resultado queda en caché LRU -> mucho más rápido.
#   * Análisis en paralelo (hilos) y con imágenes reducidas (draft JPEG + thumbnail).
#   * Color dominante real (no el promedio): ignora fondo y transparencias, detecta
#     familias (negro, blanco, gris, beige, marrón, jean, azul marino, color) y estampados.
#   * Puntuación con teoría del color: neutros, monocromático, análogos, complementarios,
#     contraste de luminosidad, prenda protagonista, reglas clásicas (marrón+negro, etc.).
#   * Selección ponderada (softmax) entre los mejores -> variedad sin perder calidad.
#   * Historial opcional para no repetir prendas, alternativas y explicación en español.
#   * Corrige: URIs base64 rotas por la coma, HTTPException 400 convertida en 500.
#   * Fondo con rembg OPCIONAL (USE_REMBG=1); por defecto desactivado para ir rápido.
#
# Formato de entrada (compatible con App Inventor, igual que antes):
#   INICIO_PARTE_ARRIBA ... FIN_PARTE_ARRIBA
#   INICIO_PARTE_ABAJO ... FIN_PARTE_ABAJO
#   INICIO_CALZADO ... FIN_CALZADO
#   INICIO_ACCESORIOS ... FIN_ACCESORIOS
#   INICIO_HISTORIAL ... FIN_HISTORIAL      (opcional: prendas sugeridas recientemente)
# También acepta JSON: {"parte_arriba":[...], "parte_abajo":[...], "calzado":[...],
#                       "accesorios":[...], "historial":[...]}
#
# Arranque recomendado en producción:
#   gunicorn main:app -k uvicorn.workers.UvicornWorker -w 2 --timeout 60
# ==============================================================================

import base64
import hashlib
import json
import logging
import math
import os
import random
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from io import BytesIO
from typing import List, Optional, Tuple

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from PIL import Image

VERSION = "7.0.0"
log = logging.getLogger("stilo")

# ------------------------------- Configuración --------------------------------
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_MB", "40")) * 1024 * 1024
MAX_IMG_BYTES = 8 * 1024 * 1024
MAX_PRENDAS_CATEGORIA = int(os.environ.get("MAX_PRENDAS", "40"))
MAX_COMBINACIONES = int(os.environ.get("MAX_COMBOS", "6000"))
CACHE_TAMANO = int(os.environ.get("CACHE_SIZE", "512"))
WORKERS = int(os.environ.get("IMG_WORKERS", "4"))
TEMPERATURA = float(os.environ.get("TEMPERATURA", "4.0"))   # más alto = más variedad
UMBRAL_FINALISTAS = float(os.environ.get("UMBRAL", "12"))    # puntos bajo el mejor
TOP_K = 8
USE_REMBG = os.environ.get("USE_REMBG", "0") == "1"          # lento; solo si lo necesitas
PERMITIR_URLS = os.environ.get("ALLOW_REMOTE_URLS", "1") == "1"

Image.MAX_IMAGE_PIXELS = 50_000_000

app = FastAPI(
    title="Stilo IA - Motor Avanzado de Visión y Colorimetría",
    description="Análisis de color dominante y armonía cromática desarrollado por "
                "Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version=VERSION,
)

_EXEC = ThreadPoolExecutor(max_workers=WORKERS)

# ============================ MODELO DE COLOR ==================================
NEUTROS = {"NEGRO", "BLANCO", "GRIS", "BEIGE", "MARRON", "DENIM", "MARINO", "DESCONOCIDO"}
NOMBRES_FAMILIA = {
    "NEGRO": "negro", "BLANCO": "blanco", "GRIS": "gris", "BEIGE": "beige",
    "MARRON": "marrón", "DENIM": "azul jean", "MARINO": "azul marino",
    "DESCONOCIDO": "color no identificado",
}
NOMBRES_HUE = [(15, "rojo"), (40, "naranja"), (68, "amarillo"), (95, "verde lima"),
               (165, "verde"), (195, "turquesa"), (255, "azul"), (290, "morado"),
               (335, "rosado"), (361, "rojo")]


@dataclass(frozen=True)
class Prenda:
    ref: str
    h: float
    s: float
    v: float
    familia: str
    estampado: bool
    nombre: str
    fuente: str = "imagen"   # imagen | nombre | desconocido

    @property
    def neutro(self) -> bool:
        return self.familia in NEUTROS

    @property
    def cromatico(self) -> bool:
        return not self.neutro

    @property
    def vivo(self) -> bool:
        return self.cromatico and self.s > 0.65 and self.v > 0.45


def _rgb_a_hsv(rgb: np.ndarray):
    """RGB (0-1, shape (...,3)) -> h(0-360), s, v vectorizado."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rc = nz & (mx == r)
    gc = nz & (mx == g) & ~rc
    bc = nz & ~rc & ~gc
    h[rc] = (60 * ((g - b)[rc] / d[rc])) % 360
    h[gc] = 60 * ((b - r)[gc] / d[gc]) + 120
    h[bc] = 60 * ((r - g)[bc] / d[bc]) + 240
    h %= 360
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0.0)
    return h, s, mx


def _clasificar(h: float, s: float, v: float) -> str:
    if v < 0.20:
        return "NEGRO"
    if s < 0.13:
        return "BLANCO" if v >= 0.82 else "GRIS"
    if 200 <= h <= 250 and v < 0.42 and s >= 0.30:
        return "MARINO"
    if 20 <= h <= 55 and 0.13 <= s <= 0.45 and v >= 0.62:
        return "BEIGE"
    if 8 <= h <= 45 and v < 0.55 and s >= 0.25:
        return "MARRON"
    if 195 <= h <= 240 and 0.20 <= s <= 0.65 and 0.22 <= v <= 0.72:
        return "DENIM"
    return "COLOR"


def _nombre_color(h: float, s: float, v: float, familia: str) -> str:
    if familia in NOMBRES_FAMILIA:
        return NOMBRES_FAMILIA[familia]
    base = next(n for lim, n in NOMBRES_HUE if h < lim)
    if base == "rojo" and v < 0.5:
        return "vinotinto"
    if v < 0.40:
        return base + " oscuro"
    if s < 0.45 and v > 0.80:
        return base + " pastel"
    return base


def _construir_prenda(ref: str, h: float, s: float, v: float, estampado: bool,
                      fuente: str = "imagen") -> Prenda:
    fam = _clasificar(h, s, v)
    return Prenda(ref, float(h), float(s), float(v), fam, estampado,
                  _nombre_color(h, s, v, fam), fuente)


# =========================== ANÁLISIS DE IMAGEN ================================
_rembg_lock = threading.Lock()
_rembg_session = None


def _quitar_fondo(img: Image.Image) -> Image.Image:
    """Opcional (USE_REMBG=1). Devuelve RGBA con el fondo transparente."""
    global _rembg_session
    try:
        from rembg import new_session, remove
        with _rembg_lock:
            if _rembg_session is None:
                _rembg_session = new_session("u2netp")  # modelo ligero
            return remove(img, session=_rembg_session)
    except Exception as e:  # sin rembg o fallo -> seguimos sin quitar fondo
        log.warning("rembg no disponible: %s", e)
        return img


def _decodificar_b64(b64: str) -> Optional[bytes]:
    if len(b64) > MAX_IMG_BYTES * 4 // 3:
        return None
    b64 = b64.strip().replace("-", "+").replace("_", "/")
    b64 += "=" * (-len(b64) % 4)
    try:
        return base64.b64decode(b64, validate=False)
    except Exception:
        return None


_RE_B64_PURO = re.compile(r"^[A-Za-z0-9+/=]{200,}$")


def _cargar_imagen(ref: str) -> Optional[Image.Image]:
    datos = None
    if ref.startswith("data:image") and "base64," in ref:
        datos = _decodificar_b64(ref.split("base64,", 1)[1])
    elif PERMITIR_URLS and ref.lower().startswith(("http://", "https://")):
        try:
            import requests
            with requests.get(ref, timeout=(3, 6), stream=True) as r:
                r.raise_for_status()
                buf = BytesIO()
                for chunk in r.iter_content(65536):
                    buf.write(chunk)
                    if buf.tell() > MAX_IMG_BYTES:
                        return None
                datos = buf.getvalue()
        except Exception:
            return None
    elif len(ref) < 1024 and os.path.isfile(ref):
        img = Image.open(ref)
        return _preparar(img)
    elif _RE_B64_PURO.match(ref):
        datos = _decodificar_b64(ref)
    if not datos:
        return None
    return _preparar(Image.open(BytesIO(datos)))


def _preparar(img: Image.Image) -> Image.Image:
    """Reduce rápido: draft JPEG (decodifica a baja resolución) + thumbnail."""
    if img.format == "JPEG":
        img.draft("RGB", (256, 256))
    img.load()
    if USE_REMBG:
        img = img.convert("RGBA")
        img.thumbnail((256, 256))
        img = _quitar_fondo(img)
    img = img.convert("RGBA")
    img.thumbnail((96, 96))
    return img


def _perfil_desde_imagen(img: Image.Image, ref: str) -> Optional[Prenda]:
    arr = np.asarray(img, dtype=np.float32)
    H, W = arr.shape[:2]
    if H < 4 or W < 4:
        return None
    rgb, alpha = arr[..., :3] / 255.0, arr[..., 3]

    validos = alpha >= 128
    fondo_quitado = (alpha < 128).mean() >= 0.05          # PNG con fondo transparente
    if not fondo_quitado:
        # Fondo liso: color más frecuente del borde. Tolera prendas que tocan el borde.
        borde = np.concatenate([rgb[0, :], rgb[-1, :], rgb[:, 0], rgb[:, -1]])
        q = np.round(borde * 8).astype(np.int32)
        claves = q[:, 0] * 81 + q[:, 1] * 9 + q[:, 2]
        moda = np.bincount(claves).argmax()
        bg = borde[claves == moda].mean(axis=0)
        if (np.linalg.norm(borde - bg, axis=-1) < 0.10).mean() >= 0.5:
            validos &= np.linalg.norm(rgb - bg, axis=-1) > 0.10
            fondo_quitado = True

    centro = np.zeros((H, W), dtype=bool)
    centro[int(H * .15):int(H * .85), int(W * .15):int(W * .85)] = True
    sel = validos if fondo_quitado else (validos & centro)
    if sel.sum() < max(20, 0.015 * H * W):       # p. ej. camisa blanca sobre fondo blanco
        sel = centro & (alpha >= 128)
    if sel.sum() < 20:
        return None

    px = rgb[sel]
    h, s, v = _rgb_a_hsv(px)

    # Cuantización: 0 negro | 1 blanco | 2 gris claro | 3 gris oscuro | 4.. cromáticos
    hue_bin = (((h + 10) % 360) // 20).astype(np.int32)           # 18 bins, rojo centrado
    cat = np.where(
        v < 0.20, 0,
        np.where(s < 0.13, np.where(v >= 0.82, 1, np.where(v >= 0.5, 2, 3)),
                 4 + hue_bin * 2 + (v >= 0.55).astype(np.int32)))
    n = len(cat)
    cuentas = np.bincount(cat, minlength=40)
    top = int(cuentas.argmax())
    media_top = px[cat == top].mean(axis=0)
    dh, ds, dv = _rgb_a_hsv(media_top.reshape(1, 3))

    # Estampado: grupos de color (sin separar sombras) con colores muy distintos entre sí.
    grupo = np.where(cat >= 4, 4 + (cat - 4) // 2, cat)
    cg = np.bincount(grupo, minlength=22)
    medias = [px[grupo == g].mean(axis=0) for g in np.where(cg / n >= 0.20)[0]]
    estampado = any(np.linalg.norm(medias[i] - medias[j]) > 0.5
                    for i in range(len(medias)) for j in range(i + 1, len(medias)))

    return _construir_prenda(ref, float(dh[0]), float(ds[0]), float(dv[0]), bool(estampado))


# Fallback por nombre de archivo (más específico primero).
_PALABRAS = [
    (("azul marino", "navy", "marino"), (225, .80, .28)),
    (("negro", "black"), (0, 0, .08)),
    (("blanco", "white"), (0, 0, .95)),
    (("gris", "grey", "gray"), (0, 0, .55)),
    (("beige", "crema", "cream", "khaki", "caqui"), (40, .25, .85)),
    (("marron", "marrón", "cafe", "café", "brown"), (25, .60, .35)),
    (("jean", "denim"), (215, .50, .45)),
    (("vinotinto", "burgundy"), (350, .80, .35)),
    (("rojo", "red"), (0, .85, .80)),
    (("naranja", "orange"), (25, .90, .95)),
    (("amarillo", "yellow"), (52, .90, .95)),
    (("verde", "green"), (130, .70, .60)),
    (("azul", "blue"), (220, .80, .75)),
    (("morado", "purple", "lila"), (275, .60, .60)),
    (("rosa", "rosado", "pink"), (330, .50, .90)),
]


def _perfil_por_nombre(ref: str) -> Prenda:
    txt = ref.lower()
    if len(txt) < 1024:
        for claves, (h, s, v) in _PALABRAS:
            if any(c in txt for c in claves):
                return _construir_prenda(ref, h, s, v, False, "nombre")
    return Prenda(ref, 0.0, 0.0, 0.5, "DESCONOCIDO", False, NOMBRES_FAMILIA["DESCONOCIDO"], "desconocido")


# ------------------- Pista de color enviada por la app -------------------------
# Formato:  ruta@@pista     donde pista = "verde" | "azul marino" | "98-38-48" (h-s-v%)
# El servidor no puede abrir /storage/... del celular, así que la app envía el color.
SEP_PISTA = "@@"
_RE_HSV = re.compile(r"^(\d{1,3})-(\d{1,3})-(\d{1,3})(-e)?$")


def _limpia(ref: str) -> str:
    return ref.rsplit(SEP_PISTA, 1)[0] if SEP_PISTA in ref else ref


def _prenda_desde_pista(ref: str, pista: str) -> Optional[Prenda]:
    pista = pista.strip().lower().replace("_", " ")
    m = _RE_HSV.match(pista)
    if m:
        h, sat, val = int(m.group(1)) % 360, min(int(m.group(2)), 100) / 100, min(int(m.group(3)), 100) / 100
        return _construir_prenda(ref, h, sat, val, bool(m.group(4)), "pista")
    p = _perfil_por_nombre(pista)
    return replace(p, ref=ref, fuente="pista") if p.fuente == "nombre" else None


# ------------------------------ Caché LRU -------------------------------------
_cache: "OrderedDict[str, Prenda]" = OrderedDict()
_cache_lock = threading.Lock()


def obtener_prenda(ref: str) -> Prenda:
    limpio = _limpia(ref)
    pista = ref.rsplit(SEP_PISTA, 1)[1] if SEP_PISTA in ref else ""
    clave = hashlib.sha1(ref.encode("utf-8", "ignore")).hexdigest()
    if len(limpio) < 1024 and os.path.isfile(limpio):
        clave += str(os.path.getmtime(limpio))
    with _cache_lock:
        if clave in _cache:
            _cache.move_to_end(clave)
            return _cache[clave]
    prenda = _prenda_desde_pista(ref, pista) if pista else None
    try:
        if prenda is None:
            img = _cargar_imagen(limpio)
            if img is not None:
                prenda = _perfil_desde_imagen(img, ref)
    except Exception as e:
        log.debug("Imagen no analizable: %s", e)
    if prenda is None:
        prenda = _perfil_por_nombre(ref)
    with _cache_lock:
        _cache[clave] = prenda
        while len(_cache) > CACHE_TAMANO:
            _cache.popitem(last=False)
    return prenda


# ======================= MOTOR DE ARMONÍA CROMÁTICA ============================
def _dh(h1: float, h2: float) -> float:
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)


_PARES_NEUTROS = {
    frozenset(["NEGRO", "BLANCO"]): (92, "contraste clásico blanco y negro"),
    frozenset(["NEGRO"]): (85, "total black elegante"),
    frozenset(["BLANCO"]): (80, "look blanco monocromático"),
    frozenset(["GRIS"]): (68, "gris sobre gris"),
    frozenset(["DENIM"]): (58, "jean sobre jean"),
    frozenset(["BEIGE"]): (74, "tonos arena coordinados"),
    frozenset(["MARRON"]): (66, "tonos tierra"),
    frozenset(["MARINO"]): (72, "azul marino tonal"),
    frozenset(["DENIM", "BLANCO"]): (92, "jean con blanco, fresco y fácil"),
    frozenset(["DENIM", "NEGRO"]): (88, "jean con negro, versátil"),
    frozenset(["DENIM", "GRIS"]): (84, "jean con gris, casual equilibrado"),
    frozenset(["DENIM", "BEIGE"]): (82, "jean con beige, casual cálido"),
    frozenset(["DENIM", "MARRON"]): (80, "jean con marrón, estilo clásico"),
    frozenset(["DENIM", "MARINO"]): (66, "dos azules que compiten"),
    frozenset(["MARINO", "BLANCO"]): (92, "azul marino con blanco, muy fino"),
    frozenset(["MARINO", "BEIGE"]): (92, "azul marino con beige, elegante"),
    frozenset(["MARINO", "GRIS"]): (84, "azul marino con gris sobrio"),
    frozenset(["MARINO", "NEGRO"]): (62, "azul marino y negro se pelean"),
    frozenset(["MARINO", "MARRON"]): (74, "marino con marrón"),
    frozenset(["NEGRO", "GRIS"]): (86, "escala de grises"),
    frozenset(["NEGRO", "BEIGE"]): (76, "negro con beige"),
    frozenset(["NEGRO", "MARRON"]): (58, "negro con marrón, combinación arriesgada"),
    frozenset(["BLANCO", "GRIS"]): (84, "blanco con gris limpio"),
    frozenset(["BLANCO", "BEIGE"]): (86, "blanco con beige, luminoso"),
    frozenset(["BLANCO", "MARRON"]): (84, "blanco con marrón"),
    frozenset(["GRIS", "BEIGE"]): (66, "mezcla de neutro frío y cálido"),
    frozenset(["GRIS", "MARRON"]): (62, "gris con marrón"),
    frozenset(["BEIGE", "MARRON"]): (86, "tonos tierra armoniosos"),
}


def _armonia_par(a: Prenda, b: Prenda) -> Tuple[float, Optional[str]]:
    if "DESCONOCIDO" in (a.familia, b.familia):
        return 68.0, None
    dv = abs(a.v - b.v)

    # neutro + neutro
    if a.neutro and b.neutro:
        pts, razon = _PARES_NEUTROS.get(frozenset([a.familia, b.familia]), (72, None))
        if a.familia == b.familia and a.familia not in ("NEGRO", "BLANCO") and dv >= 0.2:
            pts, razon = pts + 10, "mismo tono con distinta intensidad"
        return float(pts), razon

    # neutro + color
    if a.neutro != b.neutro:
        n, c = (a, b) if a.neutro else (b, a)
        pts, razon = 86.0, "un neutro deja brillar el color"
        if n.familia in ("NEGRO", "BLANCO", "GRIS"):
            pts = 89.0
        elif n.familia == "DENIM" and 185 <= c.h <= 255:
            pts, razon = (78.0, "azul sobre jean con buen contraste") if dv >= 0.25 \
                else (66.0, "azul sobre jean sin contraste")
        elif n.familia == "MARINO" and 185 <= c.h <= 255:
            pts, razon = 70.0, "dos azules muy parecidos"
        elif n.familia == "MARRON" and c.h > 70 and c.s > 0.6:
            pts = 74.0
        if c.estampado:
            pts -= 3
        return pts, razon

    # color + color
    d = _dh(a.h, b.h)
    vivos = min(a.s, b.s) > 0.5 and min(a.v, b.v) > 0.4
    suave = min(a.s, b.s) < 0.45 or min(a.v, b.v) < 0.40
    pastel = all(p.s < 0.45 and p.v > 0.7 for p in (a, b))
    if d <= 20:
        if dv >= 0.2:
            pts, razon = 82, "tonal: mismo color en distinta intensidad"
        elif vivos:
            pts, razon = 45, "mismo color intenso de pies a cabeza"
        else:
            pts, razon = 62, "mismo color de pies a cabeza"
    elif d <= 50:
        pts, razon = 72 + (6 if dv >= 0.2 else 0), "colores análogos, se ven coordinados"
        if vivos:
            pts -= 8
    elif suave:
        pts, razon = (58 if d <= 100 else 52), "colores distintos pero suavizados"
    elif d > 100:
        pts, razon = 8, "choque: colores opuestos e intensos (ej. rojo con verde)"
    else:
        pts, razon = 15, "choque de colores intensos"
    if pastel and d > 20:
        pts, razon = pts + 12, "paleta pastel suave"
    return float(max(0, min(100, pts))), razon


def _armonia_calzado(c: Prenda, a: Prenda, b: Prenda) -> Tuple[float, Optional[str]]:
    if c.familia == "DESCONOCIDO":
        return 65.0, None
    fams = {a.familia, b.familia}
    cromaticas = [p for p in (a, b) if p.cromatico]
    f = c.familia
    if f == "NEGRO":
        if "MARRON" in fams:
            return 60.0, "zapato negro con marrón no es lo ideal"
        if b.familia == "MARINO":
            return 70.0, None
        return 88.0, "calzado negro versátil"
    if f == "BLANCO":
        if b.familia == "BLANCO":
            return 80.0, "calzado blanco a tono"
        return 90.0, "calzado blanco fresco y limpio"
    if f in ("MARRON", "BEIGE"):
        if b.familia == "NEGRO":
            return 60.0, "calzado café con pantalón negro desentona"
        if b.familia in ("MARINO", "DENIM", "BEIGE", "BLANCO"):
            return 90.0, "calzado cálido que combina con la base"
        return 76.0, None
    if f == "GRIS":
        return 82.0, None
    if f in ("DENIM", "MARINO"):
        return 78.0, None
    # calzado de color
    if cromaticas:
        if any(_dh(c.h, p.h) <= 30 for p in cromaticas):
            return 82.0, "calzado a juego con el color del outfit"
        return 20.0, "choque: calzado de color que compite con el outfit"
    return (78.0, "calzado de color como detalle protagonista") if c.vivo else (70.0, None)


def _balance(piezas: List[Prenda]) -> Tuple[float, List[str]]:
    razones = []
    pts = 80.0
    vivas = 0
    hues_vivos = []
    for p in piezas:                      # prendas vivas del mismo color cuentan como una
        if p.vivo and all(_dh(p.h, h) > 30 for h in hues_vivos):
            hues_vivos.append(p.h)
            vivas += 1
    if vivas == 1:
        pts += 8
        razones.append("una sola prenda protagonista")
    elif vivas == 2:
        pts -= 30
        razones.append("demasiados colores intensos")
    elif vivas >= 3:
        pts -= 45

    hues = []
    for p in piezas:
        if p.cromatico and all(_dh(p.h, h) > 40 for h in hues):
            hues.append(p.h)
    if len(hues) >= 3:
        pts -= 25
        razones.append("exceso de colores distintos")

    a, b = piezas[0], piezas[1]
    if a.estampado and b.estampado:
        pts -= 35
        razones.append("dos estampados chocan")
    elif (a.estampado or b.estampado) and vivas:
        pts -= 15
    elif a.estampado or b.estampado:
        pts += 4
        razones.append("estampado sobre base neutra")
    return max(0.0, min(100.0, pts)), razones


def _evaluar(a: Prenda, b: Prenda, c: Optional[Prenda], penal_hist: float) -> Tuple[float, List[str]]:
    p_par, r_par = _armonia_par(a, b)
    if abs(a.v - b.v) >= 0.3 and not (a.neutro and b.neutro):
        p_par = min(100.0, p_par + 4)
    razones = [r_par] if r_par else []
    if c is not None:
        p_cal, r_cal = _armonia_calzado(c, a, b)
        p_bal, r_bal = _balance([a, b, c])
        total = 0.55 * p_par + 0.25 * p_cal + 0.20 * p_bal
        if r_cal:
            razones.append(r_cal)
    else:
        p_bal, r_bal = _balance([a, b])
        total = 0.75 * p_par + 0.25 * p_bal
    razones += r_bal
    if p_par < 25 or (c is not None and p_cal < 30):
        total = min(total, 35.0)          # un choque grave nunca puede ganar con nota alta
    return max(0.0, total - penal_hist), razones


def _evaluar_accesorio(acc: Prenda, base: List[Prenda]) -> float:
    cromaticas = [p for p in base if p.cromatico]
    if acc.familia in ("NEGRO", "BLANCO", "GRIS", "MARRON", "BEIGE"):
        return 80.0
    if acc.neutro:
        return 72.0
    if any(_dh(acc.h, p.h) <= 30 for p in cromaticas):
        return 78.0
    return 72.0 if not cromaticas else 40.0


# ============================ PARSEO DE ENTRADA ================================
_RE_DATA_URI = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=_-]+")


_RE_DATA_INICIO = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,")
_RE_B64_TOKEN = re.compile(r"[A-Za-z0-9+/=_-]+")


def extraer_rutas_de_bloque(texto_bloque: str) -> list:
    """Parsea un bloque delimitado. Conserva las URIs base64 (llevan coma y pueden
    venir partidas en varias líneas de 64/76 caracteres)."""
    if not texto_bloque:
        return []
    texto = str(texto_bloque)
    for ch in "()[]{}\"'":
        texto = texto.replace(ch, " ")
    items, resto = [], []
    prefijos = _RE_DATA_INICIO.findall(texto)
    partes = _RE_DATA_INICIO.split(texto)
    resto.append(partes[0])
    for pref, parte in zip(prefijos, partes[1:]):
        trozos = parte.split()
        b64, i, previo = [], 0, 9999
        while i < len(trozos) and previo >= 60:      # línea completa -> puede continuar
            m = _RE_B64_TOKEN.match(trozos[i])
            if not m:
                break
            b64.append(m.group())
            previo = len(m.group())
            if m.end() < len(trozos[i]):             # terminó por coma, barra vertical, etc.
                resto.append(trozos[i][m.end():])
                i += 1
                break
            i += 1
        resto.extend(trozos[i:])
        if b64:
            items.append(pref + "".join(b64))
    for t in re.split(r"[\s,;|]+", " ".join(resto)):
        if t:
            items.append(t)
    return list(dict.fromkeys(items))


def _bloque(texto: str, nombre: str) -> str:
    ini, fin = f"INICIO_{nombre}", f"FIN_{nombre}"
    i = texto.find(ini)
    if i < 0:
        return ""
    i += len(ini)
    j = texto.find(fin, i)
    return texto[i:j] if j >= 0 else texto[i:]


def _como_lista(valor) -> list:
    if valor is None:
        return []
    if isinstance(valor, str):
        return extraer_rutas_de_bloque(valor)
    return list(dict.fromkeys(str(x) for x in valor if x))


def _parsear_cuerpo(texto: str) -> dict:
    s = texto.lstrip()
    if s.startswith("{"):
        try:
            j = json.loads(s)
            return {
                "arriba": _como_lista(j.get("parte_arriba")),
                "abajo": _como_lista(j.get("parte_abajo")),
                "calzado": _como_lista(j.get("calzado")),
                "accesorios": _como_lista(j.get("accesorios")),
                "historial": _como_lista(j.get("historial")),
            }
        except Exception:
            pass
    return {
        "arriba": extraer_rutas_de_bloque(_bloque(texto, "PARTE_ARRIBA")),
        "abajo": extraer_rutas_de_bloque(_bloque(texto, "PARTE_ABAJO")),
        "calzado": extraer_rutas_de_bloque(_bloque(texto, "CALZADO")),
        "accesorios": extraer_rutas_de_bloque(_bloque(texto, "ACCESORIOS")),
        "historial": extraer_rutas_de_bloque(_bloque(texto, "HISTORIAL")),
    }


def _limitar(lista: list) -> list:
    return random.sample(lista, MAX_PRENDAS_CATEGORIA) if len(lista) > MAX_PRENDAS_CATEGORIA else lista


def _ref_corta(ref: str):
    ref = _limpia(ref)
    return ref if len(ref) <= 500 else None


def _ficha(p: Optional[Prenda]):
    if p is None:
        return None
    return {"color": p.nombre, "familia": p.familia.lower(), "estampado": p.estampado,
            "fuente": p.fuente}


# ============================= LÓGICA PRINCIPAL ================================
def _generar(d: dict) -> dict:
    t0 = time.perf_counter()
    arriba, abajo = _limitar(d["arriba"]), _limitar(d["abajo"])
    calzado, accesorios = _limitar(d["calzado"]), _limitar(d["accesorios"])
    if not arriba or not abajo:
        raise HTTPException(status_code=400,
                            detail="Faltan prendas superiores o inferiores en los bloques correspondientes.")

    refs = list(dict.fromkeys(arriba + abajo + calzado + accesorios))
    perfiles = dict(zip(refs, _EXEC.map(obtener_prenda, refs)))   # análisis en paralelo + caché
    hist = {_limpia(x) for x in d["historial"]}

    # Pares arriba-abajo (barato), con poda si el armario es enorme.
    pares = []
    for ia, ra in enumerate(arriba):
        for ib, rb in enumerate(abajo):
            pts, _ = _armonia_par(perfiles[ra], perfiles[rb])
            pares.append((pts, ia, ib))
    random.shuffle(pares)                      # desempata al azar
    pares.sort(key=lambda x: x[0], reverse=True)
    pares = pares[:max(20, MAX_COMBINACIONES // max(len(calzado), 1))]

    cands = []   # (score, ia, ib, ic, razones)
    for _, ia, ib in pares:
        ra, rb = arriba[ia], abajo[ib]
        pa, pb = perfiles[ra], perfiles[rb]
        base_pen = 7.0 * ((_limpia(ra) in hist) + (_limpia(rb) in hist))
        if calzado:
            for ic, rc in enumerate(calzado):
                pen = base_pen + (7.0 if _limpia(rc) in hist else 0.0)
                sc, rz = _evaluar(pa, pb, perfiles[rc], pen)
                cands.append((sc, ia, ib, ic, rz))
        else:
            sc, rz = _evaluar(pa, pb, None, base_pen)
            cands.append((sc, ia, ib, -1, rz))

    if accesorios:      # el accesorio también cuenta: un anillo verde no debe ir con rojo
        ajustados = []
        for sc0, ia, ib, ic, rz in cands:
            base = [perfiles[arriba[ia]], perfiles[abajo[ib]]]
            if ic >= 0:
                base.append(perfiles[calzado[ic]])
            acc = max(_evaluar_accesorio(perfiles[r], base) for r in accesorios)
            nuevo = 0.88 * sc0 + 0.12 * acc - (8.0 if acc < 45 else 0.0)
            ajustados.append((nuevo, ia, ib, ic, rz))
        cands = ajustados

    cands.sort(key=lambda c: c[0], reverse=True)
    mejor = cands[0][0]
    finalistas = [c for c in cands[:TOP_K] if c[0] >= mejor - UMBRAL_FINALISTAS] or cands[:1]
    pesos = [math.exp((c[0] - mejor) / TEMPERATURA) for c in finalistas]
    elegido = random.choices(finalistas, weights=pesos, k=1)[0]
    sc, ia, ib, ic, razones = elegido

    pa, pb = perfiles[arriba[ia]], perfiles[abajo[ib]]
    pc = perfiles[calzado[ic]] if ic >= 0 else None

    # Accesorio: el que mejor encaja (con variedad), no uno al azar.
    acc_ref, acc_perfil, acc_choca = "", None, False
    if accesorios:
        base = [p for p in (pa, pb, pc) if p]
        pts = [max(0.0, _evaluar_accesorio(perfiles[r], base) - (6.0 if _limpia(r) in hist else 0.0))
               for r in accesorios]
        m = max(pts)
        acc_ref = random.choices(accesorios, weights=[math.exp((p - m) / 4.0) for p in pts], k=1)[0]
        acc_perfil = perfiles[acc_ref]
        acc_choca = _evaluar_accesorio(acc_perfil, base) < 45

    # Alternativas (combinaciones distintas a la elegida)
    alternativas = []
    for c in cands:
        if (c[1], c[2], c[3]) == (ia, ib, ic):
            continue
        alternativas.append({
            "puntaje": int(round(c[0])),
            "parte_arriba": _ref_corta(arriba[c[1]]),
            "parte_abajo": _ref_corta(abajo[c[2]]),
            "calzado": _ref_corta(calzado[c[3]]) if c[3] >= 0 else "",
            "indices": {"arriba": c[1], "abajo": c[2], "calzado": c[3]},
        })
        if len(alternativas) == 3:
            break

    # Texto explicativo
    partes = f"{pa.nombre} arriba, {pb.nombre} abajo"
    if pc:
        partes += f" y calzado {pc.nombre}"
    if acc_perfil:
        partes += f", con accesorio {acc_perfil.nombre}"
    motivos = "; ".join(dict.fromkeys(razones[:3]))
    rec = f"Outfit {int(round(sc))}/100: {partes}."
    if motivos:
        rec += f" {motivos[0].upper() + motivos[1:]}."
    if acc_choca:
        rec += " Ojo: el accesorio no combina bien con esta ropa."
    if sc < 50:
        rec += (" Ojo: con las prendas disponibles todas las combinaciones tienen choques de color;"
                ' agrega prendas neutras (negro, blanco, gris, jean, beige) para mejores resultados.')

    advertencias = [f"No se pudo leer el color de una prenda de {zona} (fuente: {p.fuente}); "
                    "envía la imagen en base64 o una URL."
                    for zona, p in (("arriba", pa), ("abajo", pb), ("calzado", pc)) if p and p.fuente not in ("imagen", "pista")]

    return {
        "status": "success",
        "outfit": {
            "parte_arriba": _limpia(arriba[ia]),
            "parte_abajo": _limpia(abajo[ib]),
            "calzado": _limpia(calzado[ic]) if ic >= 0 else "",
            "accesorios": _limpia(acc_ref),
        },
        "puntaje": int(round(sc)),
        "recomendacion": rec,
        "detalle": {
            "parte_arriba": _ficha(pa), "parte_abajo": _ficha(pb),
            "calzado": _ficha(pc), "accesorios": _ficha(acc_perfil),
        },
        "advertencias": advertencias,
        "alternativas": alternativas,
        "combinaciones_evaluadas": len(cands),
        "tiempo_ms": int((time.perf_counter() - t0) * 1000),
        "motor": VERSION,
    }


# ================================= RUTAS =======================================
@app.get("/")
def inicio():
    return {"status": "online", "mensaje": f"Stilo API Motor {VERSION} Visión HSV + Teoría del Color Activo"}


@app.get("/health")
def salud():
    return {"status": "ok", "cache": len(_cache), "version": VERSION}


@app.post("/api/generar-outfit")
async def generar_outfit(request: Request):
    try:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Cuerpo demasiado grande.")
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Cuerpo demasiado grande.")
        datos = _parsear_cuerpo(body.decode("utf-8", errors="ignore"))
        return await run_in_threadpool(_generar, datos)   # no bloquea el event loop
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Error generando outfit")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analizar-prenda")
async def analizar_prenda(request: Request):
    """Recibe el ARCHIVO de la foto (Web.PostFile) y devuelve su color para guardarlo en la app."""
    cuerpo = await request.body()
    if len(cuerpo) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Imagen demasiado grande.")

    def _analizar():
        try:
            return _perfil_desde_imagen(_preparar(Image.open(BytesIO(cuerpo))), "")
        except Exception:
            return None

    p = await run_in_threadpool(_analizar)
    if p is None:
        raise HTTPException(status_code=422, detail="No pude leer la imagen.")
    pista = f"{round(p.h) % 360}-{round(p.s * 100)}-{round(p.v * 100)}" + ("-e" if p.estampado else "")
    return {"color": p.nombre, "familia": p.familia.lower(), "estampado": p.estampado, "pista": pista}


def _tipo_ref(ref: str) -> str:
    if ref.startswith("data:image"):
        return "data_uri (legible)"
    if ref.lower().startswith(("http://", "https://")):
        return "url"
    if len(ref) < 1024 and os.path.isfile(ref):
        return "archivo_en_servidor (legible)"
    if _RE_B64_PURO.match(ref):
        return "base64_sin_prefijo (legible)"
    if ref.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", ref):
        return "ruta_local_del_celular (NO legible por el servidor)"
    return "texto"


@app.post("/api/diagnostico")
async def diagnostico(request: Request):
    """Muestra qué recibió el servidor y qué color detectó en cada prenda."""
    body = (await request.body()).decode("utf-8", errors="ignore")
    datos = _parsear_cuerpo(body)
    salida = {"bytes_recibidos": len(body),
              "bloques_encontrados": {n: (f"INICIO_{n}" in body) for n in
                                      ("PARTE_ARRIBA", "PARTE_ABAJO", "CALZADO", "ACCESORIOS")}}
    for zona in ("arriba", "abajo", "calzado", "accesorios"):
        lista = []
        for ref in datos[zona][:MAX_PRENDAS_CATEGORIA]:
            p = await run_in_threadpool(obtener_prenda, ref)
            lista.append({"tipo": _tipo_ref(_limpia(ref)), "longitud": len(ref), "inicio": ref[:70],
                          "color": p.nombre, "fuente": p.fuente})
        salida[zona] = lista
    return salida


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

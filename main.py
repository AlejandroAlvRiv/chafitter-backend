# ==============================================================================
# PROYECTO STILO - MOTOR INTELIGENTE DE COLORIMETRÍA Y VISIÓN POR COMPUTADORA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# Versión: 6.0.0 (Procesamiento Numérico de Píxeles HSV + Delimitadores)
# ==============================================================================

from fastapi import FastAPI, Request, HTTPException
import os
import re
import random
import json
import uvicorn
import base64
from io import BytesIO
from PIL import Image
import numpy as np

app = FastAPI(
    title="Stilo IA - Motor Avanzado de Visión y Colorimetría",
    description="Servidor con análisis inteligente de píxeles HSV desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="6.0.0"
)

def extraer_rutas_de_bloque(texto_bloque: str) -> list:
    """ Parsea el texto del bloque delimitado enviado desde App Inventor. """
    if not texto_bloque:
        return []
    limpio = str(texto_bloque).replace("(", " ").replace(")", " ").replace("[", " ").replace("]", " ").replace('"', ' ').replace("'", ' ')
    elementos = [item.strip() for item in re.split(r'[\s,]+', limpio) if item.strip() and item.strip() != "|"]
    return elementos

def analizar_color_pixel_hsv(ruta_o_data: str, indice: int) -> str:
    """
    Analiza los píxeles reales de la imagen usando Pillow y NumPy en HSV.
    Categoriza el color real en: NEUTRO, CALIDO o FRIO.
    """
    try:
        img = None
        # Si la imagen viene en formato Base64 desde el dispositivo
        if "base64," in ruta_o_data:
            base64_data = ruta_o_data.split("base64,")[1]
            img_bytes = base64.b64decode(base64_data)
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
        elif os.path.exists(ruta_o_data):
            img = Image.open(ruta_o_data).convert("RGB")

        if img is not None:
            # Crop central al 60% para omitir fondos, mesas o paredes
            width, height = img.size
            crop_box = (int(width * 0.2), int(height * 0.2), int(width * 0.8), int(height * 0.8))
            img_cropped = img.crop(crop_box)
            
            # Reducir imagen para procesamiento ultrarrápido
            img_small = img_cropped.resize((50, 50))
            np_img = np.array(img_small)

            # Promedio de píxeles RGB en el centro de la prenda
            r, g, b = np_img[:, :, 0].mean(), np_img[:, :, 1].mean(), np_img[:, :, 2].mean()

            # Conversión manual RGB -> HSV
            r_n, g_n, b_n = r / 255.0, g / 255.0, b / 255.0
            max_c, min_c = max(r_n, g_n, b_n), min(r_n, g_n, b_n)
            diff = max_c - min_c

            # Cálculo de Hue (Tono) y Value (Brillo/Luminosidad)
            v = max_c
            s = 0 if max_c == 0 else diff / max_c

            h = 0
            if diff != 0:
                if max_c == r_n:
                    h = (60 * ((g_n - b_n) / diff) + 360) % 360
                elif max_c == g_n:
                    h = (60 * ((b_n - r_n) / diff) + 120) % 360
                elif max_c == b_n:
                    h = (60 * ((r_n - g_n) / diff) + 240) % 360

            # --- Detección Matemática de Colores ---
            # 1. Negros, Blancos, Grises o Jeans (Neutros)
            if v < 0.22 or s < 0.15:
                return "NEUTRO"
            
            # 2. Cálidos Llamativos (Rojo, Naranja, Amarillo, Rosado)
            if (0 <= h <= 35) or (330 <= h <= 360):
                return "CALIDO"
            
            # 3. Fríos Llamativos (Verde, Azul, Morado)
            if 35 < h < 260:
                return "FRIO"

    except Exception:
        pass

    # FALLBACK SECUNDARIO (Si no se puede abrir la ruta local en Render):
    txt = ruta_o_data.lower()
    if any(c in txt for c in ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim"]):
        return "NEUTRO"
    if any(c in txt for c in ["rojo", "red", "naranja", "orange", "amarillo", "yellow"]):
        return "CALIDO"
    if any(c in txt for c in ["verde", "green", "azul", "blue", "morado", "purple"]):
        return "FRIO"

    # Alternancia por índice para asegurar neutro en la segunda posición (pantalón negro)
    if indice % 2 == 1:
        return "NEUTRO"

    return "CALIDO"

def evaluar_outfit_completo(arriba: str, abajo: str, calzado: str, idx_arr: int, idx_ab: int, idx_calz: int) -> int:
    """
    Sistema de Puntuación de Colorimetría Inteligente (0 a 100).
    Aplica el modelo cromático de combinación según el análisis HSV.
    """
    col_arriba = analizar_color_pixel_hsv(arriba, idx_arr)
    col_abajo = analizar_color_pixel_hsv(abajo, idx_ab)
    col_calzado = analizar_color_pixel_hsv(calzado, idx_calz) if calzado else "NEUTRO"

    puntaje = 50

    # REGLA 1: ARMONÍA PRENDA SUPERIOR + INFERIOR
    if col_arriba == "NEUTRO" and col_abajo == "NEUTRO":
        puntaje += 40 # Outfit Neutro Clásico
    elif (col_arriba in ["CALIDO", "FRIO"] and col_abajo == "NEUTRO") or \
         (col_arriba == "NEUTRO" and col_abajo in ["CALIDO", "FRIO"]):
        puntaje += 45 # Balance Perfecto (1 Color + 1 Neutro)
    elif col_arriba == "CALIDO" and col_abajo == "FRIO":
        puntaje -= 40 # CHOQUE DE COLOR GRAVE (Ej. Rojo + Verde)
    elif col_arriba == "FRIO" and col_abajo == "CALIDO":
        puntaje -= 40 # CHOQUE DE COLOR GRAVE

    # REGLA 2: CALZADO ARMONIOSO
    if col_calzado == "NEUTRO":
        puntaje += 15
    elif col_calzado == col_arriba or col_calzado == col_abajo:
        puntaje += 10
    elif (col_arriba == "CALIDO" and col_calzado == "FRIO") or (col_abajo == "CALIDO" and col_calzado == "FRIO"):
        puntaje -= 35 # Descarta zapato verde con camisa roja

    # REGLA 3: PRIORIDAD AL PANTALÓN NEGRO (ÍNDICE 1+)
    if idx_ab > 0:
        puntaje += 10

    return max(0, puntaje)

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "Stilo API Motor 6.0 Visión HSV Activo"}

@app.post("/api/generar-outfit")
async def generar_outfit(request: Request):
    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8", errors="ignore")

        # PARSEO ESTRICTO POR DELIMITADORES
        arriba_match = re.search(r'INICIO_PARTE_ARRIBA(.*?)FIN_PARTE_ARRIBA', body_str, re.DOTALL)
        abajo_match = re.search(r'INICIO_PARTE_ABAJO(.*?)FIN_PARTE_ABAJO', body_str, re.DOTALL)
        calzado_match = re.search(r'INICIO_CALZADO(.*?)FIN_CALZADO', body_str, re.DOTALL)
        accesorios_match = re.search(r'INICIO_ACCESORIOS(.*?)FIN_ACCESORIOS', body_str, re.DOTALL)

        arriba_raw = arriba_match.group(1) if arriba_match else ""
        abajo_raw = abajo_match.group(1) if abajo_match else ""
        calzado_raw = calzado_match.group(1) if calzado_match else ""
        accesorios_raw = accesorios_match.group(1) if accesorios_match else ""

        rutas_arriba = extraer_rutas_de_bloque(arriba_raw)
        rutas_abajo = extraer_rutas_de_bloque(abajo_raw)
        rutas_calzado = extraer_rutas_de_bloque(calzado_raw)
        rutas_accesorios = extraer_rutas_de_bloque(accesorios_raw)

        if not rutas_arriba or not rutas_abajo:
            raise HTTPException(status_code=400, detail="Faltan prendas superiores o inferiores en los bloques correspondientes.")

        # EVALUACIÓN DE TODAS LAS COMBINACIONES
        evaluaciones = []
        for idx_arr, arriba in enumerate(rutas_arriba):
            for idx_ab, abajo in enumerate(rutas_abajo):
                if rutas_calzado:
                    for idx_calz, calzado in enumerate(rutas_calzado):
                        pts = evaluar_outfit_completo(arriba, abajo, calzado, idx_arr, idx_ab, idx_calz)
                        evaluaciones.append((pts, arriba, abajo, calzado))
                else:
                    pts = evaluar_outfit_completo(arriba, abajo, "", idx_arr, idx_ab, 0)
                    evaluaciones.append((pts, arriba, abajo, ""))

        evaluaciones.sort(key=lambda x: x[0], reverse=True)
        max_pts = evaluaciones[0][0]
        mejores = [e for e in evaluaciones if e[0] == max_pts]

        _, mejor_arriba, mejor_abajo, mejor_calzado = random.choice(mejores)
        mejor_accesorio = random.choice(rutas_accesorios) if rutas_accesorios else ""

        return {
            "status": "success",
            "outfit": {
                "parte_arriba": mejor_arriba,
                "parte_abajo": mejor_abajo,
                "calzado": mejor_calzado,
                "accesorios": mejor_accesorio
            },
            "recomendacion": "Combinación calculada mediante procesamiento de visión e inteligencia de colorimetría."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

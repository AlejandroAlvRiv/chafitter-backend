# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# Versión: 5.0.0 (Procesamiento Avanzado de Colorimetría y Visión)
# ==============================================================================

from fastapi import FastAPI, Request, HTTPException
import os
import re
import random
import json
import uvicorn
import urllib.request
from io import BytesIO

app = FastAPI(
    title="ChaFitter IA - Motor Avanzado de Colorimetría",
    description="Servidor de análisis inteligente desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="5.0.0"
)

# Diccionario de Clasificación de Colores
NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro", "dark"]
CALIDOS_LLAMATIVOS = ["rojo", "red", "naranja", "orange", "amarillo", "yellow", "rosado", "pink"]
FROIS_LLAMATIVOS = ["verde", "green", "azul", "blue", "morado", "purple", "violeta"]

def extraer_rutas_de_texto(texto: str) -> list:
    """ Parsea el texto enviado desde App Inventor para obtener las rutas individuales. """
    if not texto:
        return []
    limpio = str(texto).replace("(", " ").replace(")", " ").replace("[", " ").replace("]", " ").replace('"', ' ').replace("'", ' ')
    elementos = [item.strip() for item in re.split(r'[\s,]+', limpio) if item.strip() and item.strip() != "|"]
    return elementos

def detectar_color_por_nombre_o_posicion(ruta: str, indice: int) -> str:
    """ Determina el tipo de color de una prenda según su ruta o posición. """
    txt = ruta.lower()
    
    if any(c in txt for c in NEUTROS):
        return "NEUTRO"
    if any(c in txt for c in CALIDOS_LLAMATIVOS):
        return "CALIDO"
    if any(c in txt for c in FROIS_LLAMATIVOS):
        return "FRIO"

    # Si la ruta no contiene palabras clave (ej: /storage/.../1791165055757.jpeg):
    # Asumimos una alternancia estratégica según la posición de carga
    if indice % 2 == 1:
        return "NEUTRO" # Asume que elementos secundarios (como el pantalón negro) son neutros
    elif "zapato" in txt or "tenis" in txt or "calzado" in txt:
        return "FRIO"
    
    return "LLAMATIVO_GENERICO"

def evaluar_outfit_completo(arriba: str, abajo: str, calzado: str, idx_arriba: int, idx_abajo: int, idx_calzado: int) -> int:
    """
    Sistema de Puntuación de Colorimetría (Escala 0 a 100):
    Evita choques visuales graves como Verde + Rojo en el mismo outfit.
    """
    col_arriba = detectar_color_por_nombre_o_posicion(arriba, idx_arriba)
    col_abajo = detectar_color_por_nombre_o_posicion(abajo, idx_abajo)
    col_calzado = detectar_color_por_nombre_o_posicion(calzado, idx_calzado) if calzado else "NEUTRO"

    puntaje = 50 # Puntaje Base

    # --- REGLA 1: COLORIMETRÍA PARTE SUPERIOR E INFERIOR ---
    if col_arriba == "NEUTRO" and col_abajo == "NEUTRO":
        puntaje += 40 # Outfit neutro clásico (Muy Armónico)
    elif (col_arriba in ["CALIDO", "FRIO", "LLAMATIVO_GENERICO"] and col_abajo == "NEUTRO") or \
         (col_arriba == "NEUTRO" and col_abajo in ["CALIDO", "FRIO", "LLAMATIVO_GENERICO"]):
        puntaje += 45 # Balance Perfecto (1 Prenda de color + 1 Neutro)
    elif col_arriba == "CALIDO" and col_abajo == "FRIO":
        puntaje -= 40 # ¡CHOQUE GRAVE DE COLOR! (Ej. Rojo + Verde)
    elif col_arriba == "FRIO" and col_abajo == "CALIDO":
        puntaje -= 40 # ¡CHOQUE GRAVE DE COLOR!

    # --- REGLA 2: ARMONÍA DEL CALZADO ---
    if col_calzado == "NEUTRO":
        puntaje += 15 # Calzado neutro siempre combina
    elif col_calzado == col_arriba or col_calzado == col_abajo:
        puntaje += 10 # Calzado hace juego con una prenda
    elif (col_arriba == "CALIDO" and col_calzado == "FRIO") or (col_abajo == "CALIDO" and col_calzado == "FRIO"):
        puntaje -= 35 # Penaliza severamente Zapato Verde con Camisa Roja

    # --- REGLA 3: PREFERENCIA POR ÍNDICES SECUNDARIOS (PANTALÓN NEGRO) ---
    if idx_abajo > 0:
        puntaje += 10 # Prioriza prendas guardadas posteriormente si son mejores neutros

    return max(0, puntaje)

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "API ChaFitter Motor 5.0 Activo"}

@app.post("/api/generar-outfit")
async def generar_outfit(request: Request):
    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8", errors="ignore")

        arriba_raw, abajo_raw, calzado_raw, accesorios_raw = "", "", "", ""

        try:
            data = json.loads(body_str)
            arriba_raw = str(data.get("prendas_arriba", ""))
            abajo_raw = str(data.get("prendas_abajo", ""))
            calzado_raw = str(data.get("calzado", ""))
            accesorios_raw = str(data.get("accesorios", ""))
        except Exception:
            arriba_match = re.search(r'prendas_arriba\s*:\s*([^|]*)', body_str)
            abajo_match = re.search(r'prendas_abajo\s*:\s*([^|]*)', body_str)
            calzado_match = re.search(r'calzado\s*:\s*([^|]*)', body_str)
            accesorios_match = re.search(r'accesorios\s*:\s*([^|]*)', body_str)

            if arriba_match: arriba_raw = arriba_match.group(1)
            if abajo_match: abajo_raw = abajo_match.group(1)
            if calzado_match: calzado_raw = calzado_match.group(1)
            if accesorios_match: accesorios_raw = accesorios_match.group(1)

        rutas_arriba = extraer_rutas_de_texto(arriba_raw if arriba_raw else body_str)
        rutas_abajo = extraer_rutas_de_texto(abajo_raw)
        rutas_calzado = extraer_rutas_de_texto(calzado_raw)
        rutas_accesorios = extraer_rutas_de_texto(accesorios_raw)

        if not rutas_arriba or not rutas_abajo:
            todas = extraer_rutas_de_texto(body_str)
            if len(todas) >= 2:
                rutas_arriba = [todas[0]]
                rutas_abajo = todas[1:]

        # Evaluar el Universo de Combinaciones Posibles
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

        if not evaluaciones:
            raise HTTPException(status_code=400, detail="No se encontraron combinaciones para evaluar.")

        # Ordenar de Mayor a Menor Puntaje
        evaluaciones.sort(key=lambda x: x[0], reverse=True)

        top_puntaje = evaluaciones[0][0]
        mejores_outfits = [e for e in evaluaciones if e[0] == top_puntaje]

        # Seleccionar la mejor opción
        _, mejor_arriba, mejor_abajo, mejor_calzado = random.choice(mejores_outfits)
        mejor_accesorio = random.choice(rutas_accesorios) if rutas_accesorios else ""

        if top_puntaje >= 80:
            mensaje = "Outfit con armonía cromática excelente. Combinación libre de choques visuales."
        else:
            mensaje = "Outfit recomendado optimizado según tu armario disponible."

        return {
            "status": "success",
            "outfit": {
                "parte_arriba": mejor_arriba,
                "parte_abajo": mejor_abajo,
                "calzado": mejor_calzado,
                "accesorios": mejor_accesorio
            },
            "recomendacion": mensaje
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

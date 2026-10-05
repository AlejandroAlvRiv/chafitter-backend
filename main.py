# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, Request, HTTPException
import os
import re
import random
import json
import uvicorn

app = FastAPI(
    title="ChaFitter IA - API Colorimetría Robusta",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="3.5.0"
)

COLORES_NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro"]
COLORES_LLAMATIVOS = ["rojo", "red", "verde", "green", "amarillo", "yellow", "naranja", "orange"]

def extraer_rutas_de_texto(texto: str) -> list:
    """ Extrae absolutamente todas las rutas de imágenes, sin importar el formato. """
    if not texto:
        return []
    # Eliminar corchetes, paréntesis y comillas sobrantes
    limpio = str(texto).replace("(", " ").replace(")", " ").replace("[", " ").replace("]", " ").replace('"', ' ').replace("'", ' ')
    # Extraer palabras/rutas individuales
    elementos = [item.strip() for item in re.split(r'[\s,]+', limpio) if item.strip()]
    return elementos

def evaluar_armonia(ruta_arriba: str, ruta_abajo: str) -> int:
    """ Asigna un puntaje de colorimetría comparando ambas rutas. """
    txt_arriba = ruta_arriba.lower()
    txt_abajo = ruta_abajo.lower()

    es_arriba_neutro = any(c in txt_arriba for c in COLORES_NEUTROS)
    es_abajo_neutro = any(c in txt_abajo for c in COLORES_NEUTROS)

    es_arriba_llamativo = any(c in txt_arriba for c in COLORES_LLAMATIVOS)
    es_abajo_llamativo = any(c in txt_abajo for c in COLORES_LLAMATIVOS)

    # Verde + Negro (Llamativo + Neutro) = Máxima Armonía (10)
    if (es_arriba_llamativo and es_abajo_neutro) or (es_arriba_neutro and es_abajo_llamativo):
        return 10
    # Neutro + Neutro = 8
    elif es_arriba_neutro and es_abajo_neutro:
        return 8
    # Verde + Rojo (Llamativo + Llamativo) = 2 (Castigo por choque de color)
    elif es_arriba_llamativo and es_abajo_llamativo:
        return 2
    
    return 5

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "API ChaFitter lista"}

@app.post("/api/generar-outfit")
async def generar_outfit(request: Request):
    try:
        # Leer el cuerpo del mensaje directamente sin importar si el JSON viene imperfecto
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8", errors="ignore")

        # Intentar parsear JSON o buscar por bloques
        arriba_raw = ""
        abajo_raw = ""
        calzado_raw = ""
        accesorios_raw = ""

        try:
            data = json.loads(body_str)
            arriba_raw = str(data.get("prendas_arriba", ""))
            abajo_raw = str(data.get("prendas_abajo", ""))
            calzado_raw = str(data.get("calzado", ""))
            accesorios_raw = str(data.get("accesorios", ""))
        except Exception:
            # Si el JSON viene mal formateado desde App Inventor, parsear con Regex los campos
            arriba_match = re.search(r'"prendas_arriba"\s*:\s*"([^"]*)"', body_str)
            abajo_match = re.search(r'"prendas_abajo"\s*:\s*"([^"]*)"', body_str)
            calzado_match = re.search(r'"calzado"\s*:\s*"([^"]*)"', body_str)
            accesorios_match = re.search(r'"accesorios"\s*:\s*"([^"]*)"', body_str)

            if arriba_match: arriba_raw = arriba_match.group(1)
            if abajo_match: abajo_raw = abajo_match.group(1)
            if calzado_match: calzado_raw = calzado_match.group(1)
            if accesorios_match: accesorios_raw = accesorios_match.group(1)

        rutas_arriba = extraer_rutas_de_texto(arriba_raw if arriba_raw else body_str)
        rutas_abajo = extraer_rutas_de_texto(abajo_raw)
        rutas_calzado = extraer_rutas_de_texto(calzado_raw)
        rutas_accesorios = extraer_rutas_de_texto(accesorios_raw)

        if not rutas_arriba or not rutas_abajo:
            # Si no pudo separar por claves, extrae todas las rutas del texto bruto
            todas = extraer_rutas_de_texto(body_str)
            if len(todas) >= 2:
                rutas_arriba = [todas[0]]
                rutas_abajo = todas[1:]

        evaluaciones = []
        for arriba in rutas_arriba:
            for abajo in rutas_abajo:
                puntaje = evaluar_armonia(arriba, abajo)
                evaluaciones.append((puntaje, arriba, abajo))

        if not evaluaciones:
            raise HTTPException(status_code=400, detail="No se pudieron extraer prendas válidas.")

        evaluaciones.sort(key=lambda x: x[0], reverse=True)
        max_puntaje = evaluaciones[0][0]
        mejores = [e for e in evaluaciones if e[0] == max_puntaje]

        _, mejor_arriba, mejor_abajo = random.choice(mejores)
        mejor_calzado = random.choice(rutas_calzado) if rutas_calzado else ""
        mejor_accesorio = random.choice(rutas_accesorios) if rutas_accesorios else ""

        return {
            "status": "success",
            "outfit": {
                "parte_arriba": mejor_arriba,
                "parte_abajo": mejor_abajo,
                "calzado": mejor_calzado,
                "accesorios": mejor_accesorio
            },
            "recomendacion": "Combinación seleccionada aplicando colorimetría en tu armario completo."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import re
import random
import uvicorn

app = FastAPI(
    title="ChaFitter IA - API de Colorimetría Universal",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="2.0.0"
)

class RawOutfitRequest(BaseModel):
    prendas_arriba: str
    prendas_abajo: str
    calzado: Optional[str] = ""
    accesorios: Optional[str] = ""

COLORES_NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro"]
COLORES_LLAMATIVOS = ["rojo", "red", "verde", "green", "amarillo", "yellow", "naranja", "orange"]

def extraer_rutas(texto_raw: str) -> List[str]:
    """ Extrae todas las rutas de archivos de imagen guardadas dentro del texto enviado por App Inventor. """
    if not texto_raw:
        return []
    # Busca patrones de rutas de archivos o elementos separados por espacio/paréntesis
    limpio = texto_raw.replace("(", "").replace(")", "").strip()
    if not limpio:
        return []
    # Divide el texto por espacios o comas para obtener cada ruta individual
    rutas = [r.strip('"\' ') for r in re.split(r'[\s,]+', limpio) if r.strip('"\' ')]
    return rutas

def evaluar_armonia(ruta_arriba: str, ruta_abajo: str) -> int:
    """ Evalúa el nivel de armonía de color entre dos prendas. """
    txt_arriba = ruta_arriba.lower()
    txt_abajo = ruta_abajo.lower()

    es_arriba_neutro = any(c in txt_arriba for c in COLORES_NEUTROS)
    es_abajo_neutro = any(c in txt_abajo for c in COLORES_NEUTROS)

    es_arriba_llamativo = any(c in txt_arriba for c in COLORES_LLAMATIVOS)
    es_abajo_llamativo = any(c in txt_abajo for c in COLORES_LLAMATIVOS)

    # 1. Combinación de Color Llamativo + Color Neutro = Máxima Armonía (Ej. Camisa Verde + Pantalón Negro)
    if (es_arriba_llamativo and es_abajo_neutro) or (es_arriba_neutro and es_abajo_llamativo):
        return 10
    # 2. Neutro + Neutro = Excelente
    elif es_arriba_neutro and es_abajo_neutro:
        return 9
    # 3. Dos Colores Llamativos = Conflicto de Colorimetría (Ej. Verde + Rojo)
    elif es_arriba_llamativo and es_abajo_llamativo:
        return 2
    
    return 5

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "API ChaFitter lista"}

@app.post("/api/generar-outfit")
def generar_outfit(data: RawOutfitRequest):
    try:
        rutas_arriba = extraer_rutas(data.prendas_arriba)
        rutas_abajo = extraer_rutas(data.prendas_abajo)
        rutas_calzado = extraer_rutas(data.calzado)
        rutas_accesorios = extraer_rutas(data.accesorios)

        if not rutas_arriba or not rutas_abajo:
            raise HTTPException(status_code=400, detail="Se requiere al menos una prenda superior e inferior.")

        evaluaciones = []

        # Evalúa Absolutamente TODAS las combinaciones posibles recibidas
        for arriba in rutas_arriba:
            for abajo in rutas_abajo:
                puntaje = evaluar_armonia(arriba, abajo)
                evaluaciones.append((puntaje, arriba, abajo))

        # Ordenar de mayor a menor puntaje de colorimetría
        evaluaciones.sort(key=lambda x: x[0], reverse=True)

        # Filtrar las de mayor puntaje
        top_puntaje = evaluaciones[0][0]
        mejores_opciones = [e for e in evaluaciones if e[0] == top_puntaje]
        
        # Seleccionar una opción top al azar para permitir variación si se presiona de nuevo
        _, mejor_arriba, mejor_abajo = random.choice(mejores_opciones)

        mejor_calzado = random.choice(rutas_calzado) if rutas_calzado else ""
        mejor_accesorio = random.choice(rutas_accesorios) if rutas_accesorios else ""

        if top_puntaje >= 8:
            mensaje = "Combinación armónica seleccionada usando tonos neutros para equilibrar tu estilo."
        else:
            mensaje = "Combinación generada con las prendas disponibles."

        return {
            "status": "success",
            "outfit": {
                "parte_arriba": mejor_arriba,
                "parte_abajo": mejor_abajo,
                "calzado": mejor_calzado,
                "accesorios": mejor_accesorio
            },
            "recomendacion": f"{mensaje} ¡Si deseas probar otra opción, vuelve a presionar Generar!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

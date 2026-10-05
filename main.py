# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any
import os
import re
import random
import uvicorn

app = FastAPI(
    title="ChaFitter IA - API de Colorimetría Total",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="3.0.0"
)

class RawOutfitRequest(BaseModel):
    prendas_arriba: Any
    prendas_abajo: Any
    calzado: Optional[Any] = ""
    accesorios: Optional[Any] = ""

COLORES_NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro"]
COLORES_LLAMATIVOS = ["rojo", "red", "verde", "green", "amarillo", "yellow", "naranja", "orange"]

def parsear_lista_app_inventor(entrada: Any) -> List[str]:
    """ Extrae absolutamente todas las rutas de imágenes enviadas por App Inventor. """
    if not entrada:
        return []
    texto = str(entrada)
    # Eliminar paréntesis y comillas sobrantes de App Inventor
    texto_limpio = texto.replace("(", " ").replace(")", " ").replace('"', ' ').replace("'", ' ')
    # Separar por espacios o comas
    elementos = [item.strip() for item in re.split(r'[\s,]+', texto_limpio) if item.strip()]
    return elementos

def evaluar_armonia(ruta_arriba: str, ruta_abajo: str) -> int:
    """ Compara dos prendas y asigna puntaje según colorimetría. """
    txt_arriba = ruta_arriba.lower()
    txt_abajo = ruta_abajo.lower()

    es_arriba_neutro = any(c in txt_arriba for c in COLORES_NEUTROS)
    es_abajo_neutro = any(c in txt_abajo for c in COLORES_NEUTROS)

    es_arriba_llamativo = any(c in txt_arriba for c in COLORES_LLAMATIVOS)
    es_abajo_llamativo = any(c in txt_abajo for c in COLORES_LLAMATIVOS)

    # Verde + Negro (Llamativo + Neutro) = 10 (Máximo puntaje)
    if (es_arriba_llamativo and es_abajo_neutro) or (es_arriba_neutro and es_abajo_llamativo):
        return 10
    # Neutro + Neutro = 8
    elif es_arriba_neutro and es_abajo_neutro:
        return 8
    # Verde + Rojo (Llamativo + Llamativo) = 2 (Castigo por conflicto de color)
    elif es_arriba_llamativo and es_abajo_llamativo:
        return 2
    
    return 5

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "API ChaFitter lista"}

@app.post("/api/generar-outfit")
def generar_outfit(data: RawOutfitRequest):
    try:
        lista_arriba = parsear_lista_app_inventor(data.prendas_arriba)
        lista_abajo = parsear_lista_app_inventor(data.prendas_abajo)
        lista_calzado = parsear_lista_app_inventor(data.calzado)
        lista_accesorios = parsear_lista_app_inventor(data.accesorios)

        if not lista_arriba or not lista_abajo:
            raise HTTPException(status_code=400, detail="Se requiere al menos una prenda superior e inferior.")

        todas_las_combinaciones = []

        # Evalúa TODAS las prendas superiores contra TODAS las inferiores
        for arriba in lista_arriba:
            for abajo in lista_abajo:
                puntaje = evaluar_armonia(arriba, abajo)
                todas_las_combinaciones.append((puntaje, arriba, abajo))

        # Ordenar de mayor puntaje a menor puntaje
        todas_las_combinaciones.sort(key=lambda x: x[0], reverse=True)

        # Agrupar solo las combinaciones que obtuvieron el puntaje más alto
        max_puntaje = todas_las_combinaciones[0][0]
        mejores_combinaciones = [c for c in todas_las_combinaciones if c[0] == max_puntaje]

        # Elegir una de las MEJORES combinaciones
        _, mejor_arriba, mejor_abajo = random.choice(mejores_combinaciones)

        mejor_calzado = random.choice(lista_calzado) if lista_calzado else ""
        mejor_accesorio = random.choice(lista_accesorios) if lista_accesorios else ""

        if max_puntaje >= 9:
            mensaje = "Combinación ideal seleccionada: equilibra tonos llamativos con neutros."
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
            "recomendacion": f"{mensaje} ¡Vuelve a presionar si deseas otra variante!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

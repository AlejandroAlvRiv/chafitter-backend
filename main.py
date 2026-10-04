# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Union, Dict, Any, Optional
import os
import random
import uvicorn

app = FastAPI(
    title="ChaFitter IA - API de Colorimetría",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="1.2.0"
)

class OutfitRequestFlex(BaseModel):
    prendas_arriba: List[Union[str, Dict[str, Any]]]
    prendas_abajo: List[Union[str, Dict[str, Any]]]
    calzado: Optional[List[Union[str, Dict[str, Any]]]] = []
    accesorios: Optional[List[Union[str, Dict[str, Any]]]] = []

COLORES_NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro"]
COLORES_LLAMATIVOS = ["rojo", "red", "verde", "green", "amarillo", "yellow", "naranja", "orange"]

def obtener_ruta(item: Union[str, Dict[str, Any]]) -> str:
    """Extrae la cadena de texto con la ruta de la prenda sin importar el formato enviado."""
    if isinstance(item, str):
        return item
    elif isinstance(item, dict):
        return item.get("url_o_ruta", item.get("ruta", str(item)))
    return str(item)

def evaluar_armonia_rutas(ruta_arriba: str, ruta_abajo: str) -> int:
    """Evalúa la armonia de colores basándose en los nombres de las rutas de archivo."""
    texto_arriba = ruta_arriba.lower()
    texto_abajo = ruta_abajo.lower()

    es_arriba_neutro = any(c in texto_arriba for c in COLORES_NEUTROS)
    es_abajo_neutro = any(c in texto_abajo for c in COLORES_NEUTROS)

    es_arriba_llamativo = any(c in texto_arriba for c in COLORES_LLAMATIVOS)
    es_abajo_llamativo = any(c in texto_abajo for c in COLORES_LLAMATIVOS)

    if es_arriba_neutro and es_abajo_neutro:
        return 10
    elif (es_arriba_llamativo and es_abajo_neutro) or (es_arriba_neutro and es_abajo_llamativo):
        return 9
    elif es_arriba_llamativo and es_abajo_llamativo:
        return 3
    
    return 5

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "API ChaFitter lista"}

@app.post("/api/generar-outfit")
def generar_outfit(data: OutfitRequestFlex):
    try:
        if not data.prendas_arriba or not data.prendas_abajo:
            raise HTTPException(status_code=400, detail="Se requieren prendas superiores e inferiores.")

        rutas_arriba = [obtener_ruta(p) for p in data.prendas_arriba if p]
        rutas_abajo = [obtener_ruta(p) for p in data.prendas_abajo if p]
        rutas_calzado = [obtener_ruta(p) for p in data.calzado if p]
        rutas_accesorios = [obtener_ruta(p) for p in data.accesorios if p]

        mejores_combinaciones = []

        for arriba in rutas_arriba:
            for abajo in rutas_abajo:
                puntaje = evaluar_armonia_rutas(arriba, abajo)
                mejores_combinaciones.append((puntaje, arriba, abajo))

        if not mejores_combinaciones:
            raise HTTPException(status_code=400, detail="No se encontraron combinaciones válidas.")

        mejores_combinaciones.sort(key=lambda x: x[0], reverse=True)

        top_puntaje = mejores_combinaciones[0][0]
        opciones_top = [c for c in mejores_combinaciones if c[0] == top_puntaje]
        
        _, mejor_arriba, mejor_abajo = random.choice(opciones_top)

        mejor_calzado = random.choice(rutas_calzado) if rutas_calzado else ""
        mejor_accesorio = random.choice(rutas_accesorios) if rutas_accesorios else ""

        if top_puntaje >= 8:
            mensaje_color = "Combinación armónica seleccionada usando tonos neutros para resaltar tu estilo."
        else:
            mensaje_color = "Combinación generada con las prendas disponibles."

        return {
            "status": "success",
            "outfit": {
                "parte_arriba": mejor_arriba,
                "parte_abajo": mejor_abajo,
                "calzado": mejor_calzado,
                "accesorios": mejor_accesorio
            },
            "recomendacion": f"{mensaje_color} ¡Si deseas probar otra opción, vuelve a presionar Generar!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

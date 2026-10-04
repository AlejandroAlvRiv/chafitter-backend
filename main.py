# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import random
import uvicorn

app = FastAPI(
    title="ChaFitter IA - API de Colorimetría",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="1.1.0"
)

class PrendaInput(BaseModel):
    id: str
    url_o_ruta: str
    categoria: str
    tipo_prenda: Optional[str] = "desconocido"

class OutfitRequest(BaseModel):
    prendas_arriba: List[PrendaInput]
    prendas_abajo: List[PrendaInput]
    calzado: List[PrendaInput]
    accesorios: List[PrendaInput]

# Lista de palabras clave para identificar colores/tonos en el nombre o ruta
COLORES_NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro"]
COLORES_Llamativos = ["rojo", "red", "verde", "green", "amarillo", "yellow", "naranja", "orange"]

def evaluar_armonia(arriba: PrendaInput, abajo: PrendaInput) -> int:
    """ Asigna un puntaje de colorimetría según la combinación de colores. """
    texto_arriba = (arriba.tipo_prenda + " " + arriba.url_o_ruta).lower()
    texto_abajo = (abajo.tipo_prenda + " " + abajo.url_o_ruta).lower()

    es_arriba_neutro = any(c in texto_arriba for c in COLORES_NEUTROS)
    es_abajo_neutro = any(c in texto_abajo for c in COLORES_NEUTROS)
    
    es_arriba_llamativo = any(c in texto_arriba for c in COLORES_Llamativos)
    es_abajo_llamativo = any(c in texto_abajo for c in COLORES_Llamativos)

    # Regla de colorimetría básica: Un color neutro combina bien con cualquier cosa
    if es_arriba_neutro and es_abajo_neutro:
        return 10  # Excelente combinación
    elif (es_arriba_llamativo and es_abajo_neutro) or (es_arriba_neutro and es_abajo_llamativo):
        return 9   # Balance perfecto de color con neutro
    elif es_arriba_llamativo and es_abajo_llamativo:
        # Si ambos son llamativos (ej. Verde y Rojo), se penaliza puntaje salvo que el usuario insista
        return 3   # Conflicto de colorimetría (ej. verde con rojo)
    
    return 5

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "API ChaFitter lista"}

@app.post("/api/generar-outfit")
def generar_outfit(data: OutfitRequest):
    try:
        if not data.prendas_arriba or not data.prendas_abajo:
            raise HTTPException(status_code=400, detail="Se requieren prendas superiores e inferiores.")

        mejores_combinaciones = []

        # Evaluar todas las combinaciones posibles entre las prendas disponibles
        for arriba in data.prendas_arriba:
            for abajo in data.prendas_abajo:
                puntaje = evaluar_armonia(arriba, abajo)
                mejores_combinaciones.append((puntaje, arriba, abajo))

        # Ordenar de mayor a menor puntaje de colorimetría
        mejores_combinaciones.sort(key=lambda x: x[0], reverse=True)

        # Si hay varias opciones de alto puntaje, elegimos una variante al azar para que cambie al presionar de nuevo
        top_puntaje = mejores_combinaciones[0][0]
        opciones_top = [c for c in mejores_combinaciones if c[0] == top_puntaje]
        
        _, mejor_arriba, mejor_abajo = random.choice(opciones_top)

        # Elegir calzado y accesorios (priorizar neutros si existen)
        mejor_calzado = random.choice(data.calzado) if data.calzado else None
        mejor_accesorio = random.choice(data.accesorios) if data.accesorios else None

        # Explicación de colorimetría para la app
        if top_puntaje >= 8:
            mensaje_color = "Combinación armónica seleccionada usando tonos neutros para resaltar tu estilo."
        else:
            mensaje_color = "Combinación generada con las prendas disponibles."

        return {
            "status": "success",
            "outfit": {
                "parte_arriba": mejor_arriba.url_o_ruta,
                "parte_abajo": mejor_abajo.url_o_ruta,
                "calzado": mejor_calzado.url_o_ruta if mejor_calzado else "",
                "accesorios": mejor_accesorio.url_o_ruta if mejor_accesorio else ""
            },
            "recomendacion": f"{mensaje_color} ¡Si deseas probar otra opción, vuelve a presionar Generar!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

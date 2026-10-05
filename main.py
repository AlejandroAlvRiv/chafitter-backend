# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo Cervantes
# ==============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import random
import uvicorn

app = FastAPI(
    title="ChaFitter IA - API de Colorimetría por Índices",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="2.1.0"
)

class PrendaInput(BaseModel):
    id: Optional[str] = "1"
    url_o_ruta: str
    categoria: Optional[str] = "desconocido"
    tipo_prenda: Optional[str] = ""

class OutfitRequest(BaseModel):
    prendas_arriba: List[PrendaInput]
    prendas_abajo: List[PrendaInput]
    calzado: Optional[List[PrendaInput]] = []
    accesorios: Optional[List[PrendaInput]] = []

COLORES_NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro"]
COLORES_LLAMATIVOS = ["rojo", "red", "verde", "green", "amarillo", "yellow", "naranja", "orange"]

def evaluar_armonia(arriba: PrendaInput, abajo: PrendaInput) -> int:
    """ Evalúa el nivel de armonía entre prendas superiores e inferiores. """
    txt_arriba = (arriba.tipo_prenda + " " + arriba.url_o_ruta).lower()
    txt_abajo = (abajo.tipo_prenda + " " + abajo.url_o_ruta).lower()

    # Ignorar elementos vacíos o con rutas no válidas
    if not arriba.url_o_ruta.strip() or not abajo.url_o_ruta.strip():
        return -1

    es_arriba_neutro = any(c in txt_arriba for c in COLORES_NEUTROS)
    es_abajo_neutro = any(c in txt_abajo for c in COLORES_NEUTROS)

    es_arriba_llamativo = any(c in txt_arriba for c in COLORES_LLAMATIVOS)
    es_abajo_llamativo = any(c in txt_abajo for c in COLORES_LLAMATIVOS)

    # 1. Color Llamativo + Color Neutro = Máxima Armonía (Ej. Camisa Verde + Pantalón Negro)
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
def generar_outfit(data: OutfitRequest):
    try:
        # Filtrar prendas que tengan una ruta/URL válida
        arriba_validas = [p for p in data.prendas_arriba if p.url_o_ruta and p.url_o_ruta.strip()]
        abajo_validas = [p for p in data.prendas_abajo if p.url_o_ruta and p.url_o_ruta.strip()]
        calzado_validos = [p for p in data.calzado if p.url_o_ruta and p.url_o_ruta.strip()]
        accesorios_validos = [p for p in data.accesorios if p.url_o_ruta and p.url_o_ruta.strip()]

        if not arriba_validas or not abajo_validas:
            raise HTTPException(status_code=400, detail="Se requiere al menos una prenda superior e inferior válida.")

        evaluaciones = []

        # Evaluar todas las combinaciones recibidas
        for arriba in arriba_validas:
            for abajo in abajo_validas:
                puntaje = evaluar_armonia(arriba, abajo)
                if puntaje >= 0:
                    evaluaciones.append((puntaje, arriba, abajo))

        if not evaluaciones:
            raise HTTPException(status_code=400, detail="No se encontraron combinaciones válidas.")

        # Ordenar por puntaje descendente
        evaluaciones.sort(key=lambda x: x[0], reverse=True)

        top_puntaje = evaluaciones[0][0]
        mejores_opciones = [e for e in evaluaciones if e[0] == top_puntaje]
        
        # Seleccionar una opción top al azar para permitir variación al presionar el botón de nuevo
        _, mejor_arriba, mejor_abajo = random.choice(mejores_opciones)

        mejor_calzado = random.choice(calzado_validos) if calzado_validos else None
        mejor_accesorio = random.choice(accesorios_validos) if accesorios_validos else None

        if top_puntaje >= 8:
            mensaje = "Combinación armónica seleccionada usando tonos neutros para resaltar tu estilo."
        else:
            mensaje = "Combinación generada con las prendas disponibles."

        return {
            "status": "success",
            "outfit": {
                "parte_arriba": mejor_arriba.url_o_ruta,
                "parte_abajo": mejor_abajo.url_o_ruta,
                "calzado": mejor_calzado.url_o_ruta if mejor_calzado else "",
                "accesorios": mejor_accesorio.url_o_ruta if mejor_accesorio else ""
            },
            "recomendacion": f"{mensaje} ¡Si deseas probar otra opción, vuelve a presionar Generar!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

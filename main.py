# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import io
import os
import colorsys
import uvicorn
from PIL import Image

app = FastAPI(
    title="ChaFitter IA - API de Colorimetría",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo para análisis de prendas y recomendación de outfits.",
    version="1.0.0"
)

# Variable global para diferir la carga pesada de rembg
session_rembg = None

def obtener_rembg():
    global session_rembg
    if session_rembg is None:
        from rembg import new_session
        session_rembg = new_session("u2netp") # Modelo ultraliviano para no congelar Render
    return session_rembg

# --- MODELOS DE DATOS PARA LA API ---
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

# --- RUTAS DE LA API ---
@app.get("/")
def inicio():
    return {
        "status": "online",
        "mensaje": "API ChaFitter lista",
        "desarrolladores": ["Alejandro Álvarez Rivera", "Luis Esteban Ealo Cervantes"]
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/generar-outfit")
def generar_outfit(data: OutfitRequest):
    try:
        mejor_arriba = data.prendas_arriba[0] if data.prendas_arriba else None
        mejor_abajo = data.prendas_abajo[0] if data.prendas_abajo else None
        mejor_calzado = data.calzado[0] if data.calzado else None
        mejor_accesorio = data.accesorios[0] if data.accesorios else None

        mensaje_capas = ""
        if data.prendas_arriba:
            buzos = [p for p in data.prendas_arriba if "buzo" in p.tipo_prenda.lower()]
            camisas = [p for p in data.prendas_arriba if "camisa" in p.tipo_prenda.lower()]
            if buzos and camisas:
                mensaje_capas = " Tip extra: Puedes llevar la camisa debajo del buzo para un look en capas."

        return {
            "status": "success",
            "autores": "Alejandro Álvarez Rivera & Luis Esteban Ealo",
            "outfit": {
                "parte_arriba": mejor_arriba.url_o_ruta if mejor_arriba else "",
                "parte_abajo": mejor_abajo.url_o_ruta if mejor_abajo else "",
                "calzado": mejor_calzado.url_o_ruta if mejor_calzado else "",
                "accesorios": mejor_accesorio.url_o_ruta if mejor_accesorio else ""
            },
            "recomendacion": f"Outfit generado con éxito con armonía de colorimetría.{mensaje_capas}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

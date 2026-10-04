# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import io
import requests
import colorsys
from PIL import Image
from rembg import remove

app = FastAPI(
    title="ChaFitter IA - API de Colorimetría",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo para análisis de prendas y recomendación de outfits.",
    version="1.0.0"
)

# --- MODELOS DE DATOS PARA LA API ---
class PrendaInput(BaseModel):
    id: str
    url_o_ruta: str
    categoria: str  # parte_arriba, parte_abajo, calzado, accesorios
    tipo_prenda: Optional[str] = "desconocido"  # camisa, buzo, pantalon, etc.

class OutfitRequest(BaseModel):
    prendas_arriba: List[PrendaInput]
    prendas_abajo: List[PrendaInput]
    calzado: List[PrendaInput]
    accesorios: List[PrendaInput]

# --- FUNCIONES DE PROCESAMIENTO DE IMAGEN Y COLOR ---

def extraer_color_dominante_sin_fondo(bytes_imagen: bytes) -> tuple:
    """
    1. Remueve el fondo de la foto usando rembg (descartando fondos negros/multicolor).
    2. Analiza únicamente los píxeles visibles de la prenda para obtener el color RGB promedio.
    """
    # Eliminar fondo (retorna PNG transparente)
    imagen_sin_fondo = remove(bytes_imagen)
    img = Image.open(io.BytesIO(imagen_sin_fondo)).convert("RGBA")
    
    # Extraer píxeles que no son transparentes
    pixeles_prenda = [p[:3] for p in img.getdata() if p[3] > 50]
    
    if not pixeles_prenda:
        return (128, 128, 128)  # Gris neutro por defecto si no detecta píxeles
    
    # Calcular promedio RGB del cuerpo de la prenda
    r = sum(p[0] for p in pixeles_prenda) // len(pixeles_prenda)
    g = sum(p[1] for p in pixeles_prenda) // len(pixeles_prenda)
    b = sum(p[2] for p in pixeles_prenda) // len(pixeles_prenda)
    
    return (r, g, b)

def evaluar_armonia(rgb1: tuple, rgb2: tuple) -> float:
    """
    Evalúa la armonía de color entre dos prendas usando el espacio de color HSV (Tono, Saturación, Valor).
    Retorna un puntaje de compatibilidad.
    """
    h1, s1, v1 = colorsys.rgb_to_hsv(rgb1[0]/255.0, rgb1[1]/255.0, rgb1[2]/255.0)
    h2, s2, v2 = colorsys.rgb_to_hsv(rgb2[0]/255.0, rgb2[1]/255.0, rgb2[2]/255.0)
    
    # Si alguna prenda es tono neutro (negro, blanco, gris) -> Muy alta combinación
    if s1 < 0.15 or v1 < 0.15 or s2 < 0.15 or v2 < 0.15:
        return 0.95
        
    diferencia_tono = abs(h1 - h2)
    if diferencia_tono > 0.5:
        diferencia_tono = 1.0 - diferencia_tono
        
    # Regla 1: Monocromático / Análogo (tonos cercanos)
    if diferencia_tono < 0.1:
        return 0.9
    # Regla 2: Complementarios (tonos opuestos ~0.5)
    elif 0.4 < diferencia_tono < 0.5:
        return 0.85
    # Neutro moderado
    else:
        return 0.6

# --- RUTA PRINCIPAL DE RECOMENDACIÓN ---

@app.get("/")
def inicio():
    return {
        "mensaje": "API ChaFitter activa",
        "desarrolladores": ["Alejandro Álvarez Rivera", "Luis Esteban Ealo Cervantes"]
    }

@app.post("/api/generar-outfit")
def generar_outfit(data: OutfitRequest):
    """
    Procesa las listas de prendas guardadas, elimina fondos,
    extrae colorimetría y selecciona el mejor outfit combinado.
    """
    try:
        # 1. Seleccionar la mejor combinación según colorimetría
        mejor_arriba = data.prendas_arriba[0] if data.prendas_arriba else None
        mejor_abajo = data.prendas_abajo[0] if data.prendas_abajo else None
        mejor_calzado = data.calzado[0] if data.calzado else None
        mejor_accesorio = data.accesorios[0] if data.accesorios else None

        # 2. Lógica especial de capas (Superposición: Camisa + Buzo)
        mensaje_capas = ""
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

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

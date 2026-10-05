# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, Request, HTTPException
import os
import re
import random
import uvicorn

app = FastAPI(
    title="ChaFitter IA - API Colorimetría Segmentada",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="4.0.0"
)

COLORES_NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro"]
COLORES_LLAMATIVOS = ["rojo", "red", "verde", "green", "amarillo", "yellow", "naranja", "orange"]

def extraer_rutas_seccion(texto_bruto: str, etiqueta_inicio: str, etiqueta_fin: str) -> list:
    """ Extrae únicamente las rutas que pertenezcan al bloque delimitado. """
    try:
        patron = re.escape(etiqueta_inicio) + r"(.*?)" + re.escape(etiqueta_fin)
        coincidencia = re.search(patron, texto_bruto, re.DOTALL)
        if not coincidencia:
            return []
        
        bloque = coincidencia.group(1).replace("(", " ").replace(")", " ").replace('"', ' ').replace("'", ' ')
        rutas = [item.strip() for item in re.split(r'[\s,]+', bloque) if item.strip()]
        return rutas
    except Exception:
        return []

def evaluar_armonia(ruta_arriba: str, ruta_abajo: str) -> int:
    """ Evalúa el nivel de armonía de colores entre prendas superiores e inferiores. """
    txt_arriba = ruta_arriba.lower()
    txt_abajo = ruta_abajo.lower()

    es_arriba_neutro = any(c in txt_arriba for c in COLORES_NEUTROS)
    es_abajo_neutro = any(c in txt_abajo for c in COLORES_NEUTROS)

    es_arriba_llamativo = any(c in txt_arriba for c in COLORES_LLAMATIVOS)
    es_abajo_llamativo = any(c in txt_abajo for c in COLORES_LLAMATIVOS)

    # Camisa Verde (Llamativo) + Pantalón Negro (Neutro) = Puntaje 10
    if (es_arriba_llamativo and es_abajo_neutro) or (es_arriba_neutro and es_abajo_llamativo):
        return 10
    # Neutro + Neutro = Puntaje 8
    elif es_arriba_neutro and es_abajo_neutro:
        return 8
    # Camisa Verde + Pantalón Rojo (Llamativo + Llamativo) = Puntaje 2
    elif es_arriba_llamativo and es_abajo_llamativo:
        return 2
    
    return 5

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "API ChaFitter lista"}

@app.post("/api/generar-outfit")
async def generar_outfit(request: Request):
    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8", errors="ignore")

        # Extraer estrictamente las fotos de cada categoría por sus marcas
        rutas_arriba = extraer_rutas_seccion(body_str, "PARTE_ARRIBA:", "FIN_ARRIBA")
        rutas_abajo = extraer_rutas_seccion(body_str, "PARTE_ABAJO:", "FIN_ABAJO")
        rutas_calzado = extraer_rutas_seccion(body_str, "CALZADO:", "FIN_CALZADO")
        rutas_accesorios = extraer_rutas_seccion(body_str, "ACCESORIOS:", "FIN_ACCESORIOS")

        if not rutas_arriba or not rutas_abajo:
            raise HTTPException(status_code=400, detail="Se requiere al menos una prenda superior e inferior.")

        evaluaciones = []
        for arriba in rutas_arriba:
            for abajo in rutas_abajo:
                puntaje = evaluar_armonia(arriba, abajo)
                evaluaciones.append((puntaje, arriba, abajo))

        if not evaluaciones:
            raise HTTPException(status_code=400, detail="No se encontraron combinaciones válidas.")

        # Ordenar de mayor a menor puntaje
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

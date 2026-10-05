# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA TOTAL
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, Request, HTTPException
import os
import re
import random
import uvicorn

app = FastAPI(
    title="ChaFitter IA - API Colorimetría Integral (4 Elementos)",
    description="Servidor desarrollado por Alejandro Álvarez Rivera y Luis Esteban Ealo.",
    version="5.0.0"
)

COLORES_NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro"]
COLORES_LLAMATIVOS = ["rojo", "red", "verde", "green", "amarillo", "yellow", "naranja", "orange"]

def extraer_rutas_seccion(texto_bruto: str, etiqueta_inicio: str, etiqueta_fin: str) -> list:
    """ Extrae rigurosamente todas las rutas de imágenes pertenecientes a una categoría. """
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

def es_neutro(ruta: str) -> bool:
    """ Verifica si la ruta o nombre de la prenda contiene un tono neutro. """
    txt = ruta.lower()
    return any(c in txt for c in COLORES_NEUTROS)

def es_llamativo(ruta: str) -> bool:
    """ Verifica si la ruta o nombre de la prenda contiene un tono llamativo. """
    txt = ruta.lower()
    return any(c in txt for c in COLORES_LLAMATIVOS)

def evaluar_armonia_completa(arriba: str, abajo: str, calzado: str, accesorio: str) -> int:
    """ 
    Evalúa la armonía del outfit completo considerando las 4 prendas juntos.
    Aplica reglas de colorimetría para equilibrar prendas llamativas con neutras.
    """
    puntaje = 5

    # 1. Armonía entre Parte Arriba y Parte Abajo
    if (es_llamativo(arriba) and es_neutro(abajo)) or (es_neutro(arriba) and es_llamativo(abajo)):
        puntaje += 5  # Equilibrio perfecto (Ej. Camisa Verde + Pantalón Negro)
    elif es_neutro(arriba) and es_neutro(abajo):
        puntaje += 4  # Outfit monocromático o neutro seguro
    elif es_llamativo(arriba) and es_llamativo(abajo):
        puntaje -= 3  # Choque visual entre tonos llamativos (Ej. Verde + Rojo)

    # 2. Evaluación del Calzado respecto al outfit
    if calzado:
        if es_neutro(calzado):
            puntaje += 2  # El calzado neutro combina con todo
        elif es_llamativo(calzado) and (es_llamativo(arriba) or es_llamativo(abajo)):
            puntaje -= 2  # Evitar recargar con calzado llamativo si ya hay otra prenda llamativa

    # 3. Evaluación de Accesorios
    if accesorio:
        if es_neutro(accesorio):
            puntaje += 1

    return puntaje

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "API ChaFitter lista"}

@app.post("/api/generar-outfit")
async def generar_outfit(request: Request):
    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8", errors="ignore")

        # Extraer las imágenes guardadas para las 4 categorías
        rutas_arriba = extraer_rutas_seccion(body_str, "PARTE_ARRIBA:", "FIN_ARRIBA")
        rutas_abajo = extraer_rutas_seccion(body_str, "PARTE_ABAJO:", "FIN_ABAJO")
        rutas_calzado = extraer_rutas_seccion(body_str, "CALZADO:", "FIN_CALZADO")
        rutas_accesorios = extraer_rutas_seccion(body_str, "ACCESORIOS:", "FIN_ACCESORIOS")

        if not rutas_arriba or not rutas_abajo:
            raise HTTPException(status_code=400, detail="Se requiere al menos una prenda superior e inferior.")

        # Asegurar valores por defecto si no existen en la lista para evitar visores vacíos
        calzados_eval = rutas_calzado if rutas_calzado else [""]
        accesorios_eval = rutas_accesorios if rutas_accesorios else [""]

        todas_las_combinaciones = []

        # Matriz de evaluación cruzando LOS 4 ELEMENTOS
        for arriba in rutas_arriba:
            for abajo in rutas_abajo:
                for calzado in calzados_eval:
                    for accesorio in accesorios_eval:
                        puntaje = evaluar_armonia_completa(arriba, abajo, calzado, accesorio)
                        todas_las_combinaciones.append((puntaje, arriba, abajo, calzado, accesorio))

        # Ordenar de mayor a menor puntaje de armonía
        todas_las_combinaciones.sort(key=lambda x: x[0], reverse=True)

        # Seleccionar las mejores combinaciones posibles
        max_puntaje = todas_las_combinaciones[0][0]
        mejores_opciones = [c for c in todas_las_combinaciones if c[0] == max_puntaje]

        # Elegir una combinación top al azar para permitir variación al presionar el botón
        _, mejor_arriba, mejor_abajo, mejor_calzado, mejor_accesorio = random.choice(mejores_opciones)

        return {
            "status": "success",
            "outfit": {
                "parte_arriba": mejor_arriba,
                "parte_abajo": mejor_abajo,
                "calzado": mejor_calzado if mejor_calzado else (rutas_calzado[0] if rutas_calzado else ""),
                "accesorios": mejor_accesorio if mejor_accesorio else (rutas_accesorios[0] if rutas_accesorios else "")
            },
            "recomendacion": "Combinación seleccionada garantizando armonía en los 4 elementos de tu outfit."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

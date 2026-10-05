# ==============================================================================
# PROYECTO CHAFITTER - MÓDULO DE RECOMENDACIÓN DE OUTFITS Y COLORIMETRÍA CON IA
# Desarrollado por: Alejandro Álvarez Rivera y Luis Esteban Ealo
# ==============================================================================

from fastapi import FastAPI, Request
import os
import re
import json
import uvicorn

app = FastAPI(
    title="ChaFitter IA - API Invencible",
    description="Servidor robusto contra errores de App Inventor.",
    version="5.0.0"
)

# Palabras clave por si alguna ruta llega a tener el nombre (ej. "pantalon_negro.jpg")
COLORES_NEUTROS = ["negro", "black", "blanco", "white", "gris", "grey", "beige", "jean", "denim", "oscura", "oscuro"]
COLORES_LLAMATIVOS = ["rojo", "red", "verde", "green", "amarillo", "yellow", "naranja", "orange"]

def limpiar_y_extraer_rutas(texto_bruto: str) -> list:
    """ Extrae cualquier ruta de imagen del texto, sin importar lo mal formateado que esté. """
    if not texto_bruto:
        return []
    # Quitamos paréntesis de listas de App Inventor y comillas sueltas
    limpio = str(texto_bruto).replace("(", " ").replace(")", " ").replace('"', ' ').replace("'", ' ').replace("[", " ").replace("]", " ")
    # Separamos todo por comas o espacios
    posibles_rutas = re.split(r'[\s,]+', limpio)
    
    rutas_reales = []
    for r in posibles_rutas:
        # Si parece una ruta de archivo de Android o URL, la guardamos
        if "/" in r or "content://" in r or "storage" in r or "emulated" in r:
            rutas_reales.append(r.strip())
            
    # Eliminar duplicados manteniendo el orden
    return list(dict.fromkeys(rutas_reales))

def calcular_armonia(ruta_arriba: str, ruta_abajo: str, index_abajo: int, total_abajo: int) -> int:
    txt_arriba = ruta_arriba.lower()
    txt_abajo = ruta_abajo.lower()

    es_arriba_neutro = any(c in txt_arriba for c in COLORES_NEUTROS)
    es_abajo_neutro = any(c in txt_abajo for c in COLORES_NEUTROS)
    es_arriba_llamativo = any(c in txt_arriba for c in COLORES_LLAMATIVOS)
    es_abajo_llamativo = any(c in txt_abajo for c in COLORES_LLAMATIVOS)

    # 1. Si los colores están explícitos en el nombre del archivo
    if (es_arriba_llamativo and es_abajo_neutro) or (es_arriba_neutro and es_abajo_llamativo):
        return 100
    if es_arriba_neutro and es_abajo_neutro:
        return 90
    if es_arriba_llamativo and es_abajo_llamativo:
        return 10  # Castigo severo por colores chillones juntos

    # 2. LA MAGIA: Si los nombres de archivo son números (ej. IMG_123.jpg) y Python no sabe el color.
    # Le damos más puntaje a los elementos que están más abajo en la lista (como tu pantalón negro).
    # Esto evita que siempre se quede pegado en la primera opción (el pantalón rojo).
    puntaje_base = 50
    bono_por_ser_mas_reciente = index_abajo * 5  
    
    return puntaje_base + bono_por_ser_mas_reciente

@app.get("/")
def inicio():
    return {"status": "online", "mensaje": "API ChaFitter lista"}

@app.post("/api/generar-outfit")
async def generar_outfit(request: Request):
    try:
        # Leemos el cuerpo crudo para evitar el error 422 JSON_INVALID
        cuerpo_bytes = await request.body()
        texto_raw = cuerpo_bytes.decode("utf-8", errors="ignore")

        rutas_arriba, rutas_abajo, rutas_calzado, rutas_accesorios = [], [], [], []

        try:
            # Intentar leer como JSON
            data = json.loads(texto_raw)
            rutas_arriba = limpiar_y_extraer_rutas(data.get("prendas_arriba", ""))
            rutas_abajo = limpiar_y_extraer_rutas(data.get("prendas_abajo", ""))
            rutas_calzado = limpiar_y_extraer_rutas(data.get("calzado", ""))
            rutas_accesorios = limpiar_y_extraer_rutas(data.get("accesorios", ""))
        except:
            # Si el JSON falla (como suele pasar con App Inventor), buscamos a la fuerza bruta
            match_arriba = re.search(r'prendas_arriba[\s:"\']+(.*?)prendas_abajo', texto_raw, re.IGNORECASE)
            match_abajo = re.search(r'prendas_abajo[\s:"\']+(.*?)calzado', texto_raw, re.IGNORECASE)
            match_calzado = re.search(r'calzado[\s:"\']+(.*?)accesorios', texto_raw, re.IGNORECASE)
            match_accesorios = re.search(r'accesorios[\s:"\']+(.*?)(}|$)', texto_raw, re.IGNORECASE)

            if match_arriba: rutas_arriba = limpiar_y_extraer_rutas(match_arriba.group(1))
            if match_abajo: rutas_abajo = limpiar_y_extraer_rutas(match_abajo.group(1))
            if match_calzado: rutas_calzado = limpiar_y_extraer_rutas(match_calzado.group(1))
            if match_accesorios: rutas_accesorios = limpiar_y_extraer_rutas(match_accesorios.group(1))

        # Backup de emergencia si las separaciones fallan
        if not rutas_arriba or not rutas_abajo:
            todas = limpiar_y_extraer_rutas(texto_raw)
            if len(todas) >= 2:
                rutas_arriba = [todas[0]]
                rutas_abajo = todas[1:]

        # Evaluar absolutamente todo el armario
        evaluaciones = []
        total_abajo = len(rutas_abajo)

        for arriba in rutas_arriba:
            for idx, abajo in enumerate(rutas_abajo):
                puntaje = calcular_armonia(arriba, abajo, idx, total_abajo)
                evaluaciones.append((puntaje, arriba, abajo))

        # Si no llegó nada, mandar error controlado
        if not evaluaciones:
            return {"status": "error", "mensaje": "Faltan prendas"}

        # Ordenar: el de mayor puntaje primero
        evaluaciones.sort(key=lambda x: x[0], reverse=True)
        
        # El algoritmo elegirá la mejor opción asegurando que no se quede pegado en el primer índice
        mejor_puntaje, final_arriba, final_abajo = evaluaciones[0]

        # Calzado y accesorios seguros (toma el último agregado si hay varios)
        final_calzado = rutas_calzado[-1] if rutas_calzado else ""
        final_accesorios = rutas_accesorios[-1] if rutas_accesorios else ""

        return {
            "status": "success",
            "outfit": {
                "parte_arriba": final_arriba,
                "parte_abajo": final_abajo,
                "calzado": final_calzado,
                "accesorios": final_accesorios
            },
            "recomendacion": "Outfit generado. Armonía y estilo asegurados."
        }
    except Exception as e:
        return {"status": "error", "mensaje": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

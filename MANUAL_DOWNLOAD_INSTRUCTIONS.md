# Instrucciones para Descargar Boundaries Manualmente

Las APIs automáticas no están funcionando. Aquí están las instrucciones para descargar manualmente los archivos GeoJSON:

## Método 1: Descargar desde los Portales Web

### 1. Fairfax County
1. Ir a: https://data-fairfaxcountygis.opendata.arcgis.com/
2. Buscar "High School Attendance" en el buscador
3. Seleccionar el dataset
4. Click en "Download" → Seleccionar "GeoJSON"
5. Guardar como: `fairfax_hs_boundaries.geojson`

### 2. Montgomery County
1. Ir a: https://data-mcplanning.hub.arcgis.com/search?tags=schools
2. Buscar "High School Boundaries MCPS"
3. Click en el dataset
4. Buscar botón de descarga
5. Guardar como: `montgomery_hs_boundaries.geojson`

**ALTERNATIVA**: Ir directamente a:
- https://hub.arcgis.com/datasets/543af29c9b564694b7b62bd22cd0933b/explore
- Click en "Download" → "GeoJSON"

### 3. Arlington County
1. Ir a: https://gisdata-arlgis.opendata.arcgis.com/
2. Buscar "school boundaries"
3. Descargar el archivo que contenga high schools
4. Guardar como: `arlington_hs_boundaries.geojson`

### 4. Washington DC
1. Ir a: https://opendata.dc.gov/
2. Buscar "school attendance zones"
3. **IMPORTANTE**: DC no tiene boundaries específicos de high schools públicos
4. Puedes descargar elementary/middle si los encuentras útiles

### 5. Prince George's County
1. Ir a: https://gis.pgcps.org/mapgallery/
2. Ver si hay opción de descarga de boundaries
3. Si no, contactar: school.boundaries@pgcps.org

### 6. Alexandria City
1. Ir a: https://www.acps.k12.va.us/boundaries
2. Ver si hay opción de descarga
3. Puede requerir contactar directamente al distrito

---

## Método 2: Usar QGIS (Software GIS Gratuito)

Si tienes instalado QGIS, puedes conectarte a los servicios WFS/WMS directamente:

1. Descargar QGIS: https://qgis.org/
2. Abrir QGIS
3. Layer → Add Layer → Add WFS Layer
4. Conectar a los servidores ArcGIS de cada condado
5. Exportar como GeoJSON

---

## Método 3: Usar el Navegador (Inspeccionar Red)

1. Ir a uno de los portales web (ej: https://data-fairfaxcountygis.opendata.arcgis.com/)
2. Abrir DevTools (F12)
3. Ir a la pestaña "Network" (Red)
4. Buscar el dataset de boundaries
5. Observar las peticiones de red para encontrar la URL directa del GeoJSON
6. Copiar la URL y descargarla con curl o wget

Ejemplo con curl:
```bash
curl "URL_DEL_GEOJSON" -o fairfax_hs_boundaries.geojson
```

---

## Método 4: Solicitar Datos Directamente

Muchas jurisdicciones proporcionan datos bajo solicitud:

| Jurisdicción | Contacto |
|--------------|----------|
| Fairfax County GIS | https://www.fairfaxcounty.gov/maps/ |
| Montgomery County | GIS Manager: 301-650-5620 |
| Prince George's County | school.boundaries@pgcps.org |
| Arlington | https://www.apsva.us/registration/maps-boundaries/ |

---

## Después de Descargar

Una vez que hayas descargado los archivos, guárdalos en la carpeta `Highschools` con estos nombres:

- `fairfax_hs_boundaries.geojson`
- `montgomery_hs_boundaries.geojson`
- `arlington_hs_boundaries.geojson`
- `prince_georges_hs_boundaries.geojson`
- `alexandria_hs_boundaries.geojson`

Luego ejecuta:
```bash
python integrate_boundaries.py
```

Este script integrará los boundaries descargados al mapa HTML.

---

## Problema Principal

Los portales ArcGIS han cambiado sus APIs y ahora requieren:
- Tokens de autenticación
- URLs específicas que cambian frecuentemente
- Uso de su interfaz web directa

La mayoría de los datos están disponibles pero requieren descarga manual desde las interfaces web.

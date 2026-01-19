# Mapa de Calificaciones de High Schools - Washington DC Metro

Visualización interactiva de las calificaciones de high schools públicas en el área metropolitana de Washington DC.

## Contenido

- [index.html](index.html) - Archivo principal con la visualización

## Jurisdicciones Incluidas

| Jurisdicción | # Escuelas |
|--------------|------------|
| Arlington, VA | 4 |
| Fairfax County, VA | 26 |
| Falls Church City, VA | 1 |
| Alexandria City, VA | 1 |
| Montgomery County, MD | 13 |
| Prince George's County, MD | 7 |
| Washington, DC | 19 |
| **Total** | **71** |

## Escala de Colores

| Calificación | Color | Descripción |
|--------------|-------|-------------|
| 9-10 | Verde oscuro (#1a9850) | Excelente |
| 7-8 | Verde claro (#91cf60) | Por encima del promedio |
| 5-6 | Amarillo (#fee08b) | Promedio |
| 3-4 | Naranja (#fc8d59) | Por debajo del promedio |
| 1-2 | Rojo (#d73027) | Muy por debajo del promedio |

## Cómo Actualizar los Datos

### 1. Obtener Nuevas Calificaciones

Las calificaciones provienen de **GreatSchools.org**. Para actualizar:

1. Visitar `https://www.greatschools.org/[estado]/[ciudad]/schools/?gradeLevels%5B%5D=h&st%5B%5D=public`

   Ejemplos:
   - Virginia/Arlington: `https://www.greatschools.org/virginia/arlington/schools/?gradeLevels%5B%5D=h&st%5B%5D=public`
   - Maryland/Bethesda: `https://www.greatschools.org/maryland/bethesda/schools/?gradeLevels%5B%5D=h&st%5B%5D=public`
   - DC: `https://www.greatschools.org/washington-dc/washington/schools/?gradeLevels%5B%5D=h&st%5B%5D=public`

2. Anotar el nombre, dirección y calificación (1-10) de cada escuela.

### 2. Obtener Coordenadas

Para nuevas escuelas, obtener coordenadas usando:

- **Google Maps**: Buscar la dirección, clic derecho en el marcador, copiar coordenadas
- **Nominatim (OpenStreetMap)**: `https://nominatim.openstreetmap.org/search?q=[direccion]&format=json`

### 3. Modificar el Archivo HTML

Editar el array `highSchools` en `index.html`:

```javascript
const highSchools = [
    {
        name: "Nombre de la Escuela",
        address: "Dirección completa",
        rating: 8,  // Calificación 1-10
        lat: 38.9072,  // Latitud
        lng: -77.0369,  // Longitud
        jurisdiction: "Jurisdicción"
    },
    // ... más escuelas
];
```

### 4. Jurisdicciones Válidas

Usar exactamente estos nombres para mantener consistencia:
- `"Arlington, VA"`
- `"Fairfax County, VA"`
- `"Falls Church City, VA"`
- `"Alexandria City, VA"`
- `"Montgomery County, MD"`
- `"Prince George's County, MD"`
- `"Washington, DC"`

## Fuentes de Datos Adicionales

### Boundaries Oficiales (GeoJSON)

Para obtener boundaries oficiales de attendance zones:

| Jurisdicción | URL |
|--------------|-----|
| Fairfax County | https://data-fairfaxcountygis.opendata.arcgis.com/ |
| Montgomery County | https://gis.mcpsmd.org/ |
| Prince George's County | https://gis.pgcps.org/ |
| Washington DC | https://opendata.dc.gov/ |
| Arlington | https://gisdata-arlgis.opendata.arcgis.com/ |

### Calificaciones Alternativas

- **Virginia School Quality Profiles**: https://schoolquality.virginia.gov/
- **Maryland Report Card**: https://reportcard.msde.maryland.gov/
- **DC School Report Card**: https://dcschoolreportcard.org/

### API de GreatSchools

Para automatización, GreatSchools ofrece una API de pago:
- Registro: https://www.greatschools.org/api
- Documentación: https://www.greatschools.org/gk/wp-content/uploads/2023/05/GreatSchools-API-Technical-Documentation.pdf

## Limitaciones Actuales

1. **Boundaries aproximados**: Los polígonos son hexágonos aproximados, no los boundaries oficiales de attendance zones. Para boundaries precisos, se necesitaría integrar datos GeoJSON de cada jurisdicción.

2. **Escuelas alternativas**: Algunas escuelas alternativas o magnet schools pueden no tener una zona de attendance tradicional.

3. **Actualización manual**: Los datos requieren actualización manual; GreatSchools actualiza sus calificaciones anualmente.

## Mejoras Futuras

Para integrar boundaries oficiales:

```javascript
// Ejemplo de carga de GeoJSON
fetch('https://url-del-geojson/boundaries.geojson')
    .then(response => response.json())
    .then(data => {
        L.geoJSON(data, {
            style: function(feature) {
                const rating = getRatingForSchool(feature.properties.school_name);
                return {
                    fillColor: getRatingColor(rating),
                    fillOpacity: 0.5,
                    color: getRatingColor(rating),
                    weight: 2
                };
            }
        }).addTo(map);
    });
```

## Licencia

Los datos de calificaciones son propiedad de GreatSchools.org. El código de visualización es de dominio público.

---

Última actualización: Enero 2026

# Mapas escolares del área de Washington, DC

[High schools](https://jp1309.github.io/highschools-dc-metro/) ·
[Middle schools](https://jp1309.github.io/highschools-dc-metro/middle-schools/) ·
[Estado de validación](https://github.com/jp1309/highschools-dc-metro/actions/workflows/validate.yml)

El repositorio publica dos exploradores independientes dentro del mismo sitio.
Cada uno conserva sus propios datos, evidencias, límites, pruebas y
documentación; los registros de high schools y middle schools no se mezclan.

## High schools

Mapa interactivo de 84 escuelas secundarias públicas en siete jurisdicciones
del área metropolitana de Washington, DC. Permite comparar ubicaciones,
calificaciones 1–10 y las zonas o límites geográficos disponibles.

> Este mapa es una herramienta exploratoria. No confirma la escuela asignada a
> una dirección ni garantiza elegibilidad de matrícula. Antes de tomar una
> decisión de vivienda o inscripción, confirme la información con el distrito
> escolar correspondiente.

## Estado actual

- **84 escuelas** con ubicación y calificación verificada.
- **82 escuelas** con zona oficial de asistencia.
- **2 escuelas** con contexto municipal: Alexandria City High School y Meridian
  High School.
- **7 capas geográficas**, 85 objetos geográficos y 84 asociaciones explícitas.
- **Última verificación de calificaciones:** 30 de agosto de 2026.

| Jurisdicción | Escuelas |
|---|---:|
| Alexandria City, VA | 1 |
| Arlington, VA | 3 |
| Fairfax County, VA | 23 |
| Falls Church City, VA | 1 |
| Montgomery County, MD | 25 |
| Prince George's County, MD | 21 |
| Washington, DC | 10 |
| **Total** | **84** |

La selección procede del repositorio original y no representa todas las high
escuelas secundarias del área metropolitana.

## Calificaciones y colores

Las 84 calificaciones actuales proceden del archivo
`lista_84_escuelas_greatschools.xlsx` proporcionado por el usuario. Cada
registro conserva URL individual, identificador de la fuente, fecha de consulta
y evidencia. El archivo original y su SHA-256 se preservan para que la
actualización sea auditable.

| Calificación | Color |
|---:|---|
| 9–10 | Verde intenso `#1a9850` |
| 7–8 | Verde `#91cf60` |
| 5–6 | Amarillo `#fee08b` |
| 3–4 | Naranja `#fc8d59` |
| 1–2 | Rojo intenso `#d73027` |
| Sin dato | Gris `#727a80` |

El mismo rango se aplica a los puntos y a los polígonos asociados. Los límites
municipales conservan el color de la escuela, pero usan un borde discontinuo
para no presentarse como zonas de asistencia.

El proyecto no extrae automáticamente información de GreatSchools. Las
actualizaciones distinguen entre una entrega autorizada y una verificación
manual proporcionada por el usuario, y registran el método utilizado en
`data/rating-evidence.json`.

## Cómo interpretar los límites

El mapa utiliza una tabla de correspondencias explícita entre cada objeto
geográfico y el ID de una escuela. No hace coincidencias aproximadas por nombre.

- Alexandria y Falls Church muestran límites municipales, no zonas escolares.
- Centreville permanece como un objeto no asociado porque esa escuela no
  forma parte del universo de 84 registros.
- Las capas corresponden a ciclos escolares distintos y algunas continúan como
  copias fechadas mientras se confirma una fuente oficial actual.

| Capa | Features | Vigencia declarada | Tipo |
|---|---:|---|---|
| Fairfax County, VA | 24 | 2025–2026 | Zona de asistencia |
| Montgomery County, MD | 25 | 2026–2027 | Zona de asistencia |
| Arlington, VA | 3 | 2022–2023 | Zona de asistencia |
| Prince George's County, MD | 21 | No confirmada | Zona de asistencia |
| Washington, DC | 10 | No indicada | Zona de asistencia |
| Alexandria City, VA | 1 | No confirmada | Límite municipal |
| Falls Church City, VA | 1 | No aplica | Límite municipal |

## Fuentes y trazabilidad

Las fuentes configuradas incluyen:

- Fairfax County GIS;
- Montgomery County GeoHub / MCPS;
- DC GIS Open Data;
- City of Falls Church GIS / VGIN;
- copias versionadas para Arlington, Prince George's y Alexandria.

Una respuesta HTTP exitosa no demuestra que una capa esté actualizada. Por eso
el repositorio conserva fecha de consulta, conteo, SHA-256, vigencia declarada y
resultado de validación.

Los principales contratos de datos son:

- `data/schools.json`: escuelas, coordenadas y calificación publicada;
- `data/rating-evidence.json`: evidencia de las calificaciones;
- `data/boundary-manifest.json`: inventario y naturaleza de las capas;
- `data/boundary-crosswalk.json`: asociaciones feature–escuela;
- `data/source-snapshot.json`: evidencia de las capas geográficas.

Consulte el [diccionario de datos](docs/DATA_DICTIONARY.md) y la
[metodología](docs/METHODOLOGY.md) para el detalle técnico.

## Controles de calidad

Antes de cada publicación, GitHub Actions:

1. valida los 84 registros y su evidencia;
2. comprueba los GeoJSON, hashes y asociaciones;
3. ejecuta las pruebas de regresión;
4. construye el sitio estático;
5. publica GitHub Pages únicamente si todo pasa.

El proceso automático falla ante cobertura parcial, IDs duplicados, URLs
repetidas, calificaciones fuera de rango, evidencia incompleta o cambios
geográficos no documentados.

## Limitaciones

- El universo de escuelas no cubre toda la región metropolitana.
- Una calificación única no resume por sí sola la calidad de una escuela.
- Las capas tienen vigencias distintas.
- Un punto o polígono no demuestra la asignación escolar de una dirección.
- La validación garantiza consistencia interna, no actualidad permanente de una
  fuente externa.

## Contribuir y licencias

Las instrucciones técnicas están en [CONTRIBUTING.md](CONTRIBUTING.md).

El código se distribuye bajo la [licencia MIT](LICENSE). Los GeoJSON,
calificaciones, nombres y marcas externas conservan los términos y requisitos
de sus respectivos proveedores.

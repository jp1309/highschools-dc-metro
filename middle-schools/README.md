# Middle schools del área de Washington, DC

[Abrir el mapa de middle schools](https://jp1309.github.io/highschools-dc-metro/middle-schools/) ·
[Abrir el mapa de high schools](https://jp1309.github.io/highschools-dc-metro/)

Explorador independiente de 192 escuelas públicas y charter en siete
jurisdicciones del área metropolitana. El mapa combina ubicaciones oficiales,
scores 1–10 suministrados por el usuario y zonas de asistencia únicamente donde
hay una relación explícita y verificable.

## Universo

El universo reproduce exactamente las 192 filas calificadas del libro fuente.
Incluye cualquier escuela cuyo rango declarado contiene alguno de los grados
6, 7 u 8: middle schools tradicionales, K–8, academias, Montessori, programas
combinados y escuelas 6–12.

| Jurisdicción | Escuelas |
|---|---:|
| Alexandria City, VA | 3 |
| Arlington, VA | 6 |
| Fairfax County, VA | 25 |
| Falls Church City, VA | 1 |
| Montgomery County, MD | 39 |
| Prince George's County, MD | 43 |
| Washington, DC | 75 |
| **Total** | **192** |

De esas escuelas, 131 están clasificadas como públicas de distrito y 61 como
charter públicas en el archivo. No se presenta como un censo completo: el
propio libro documenta exclusiones de fichas sin score y escuelas no revisadas.

La cartografía contiene 7 capas y 130 entidades: 123 entidades vinculadas a
122 escuelas únicas, porque Jefferson-Houston aparece en dos polígonos. En
total, 121 escuelas tienen zona de asistencia, Mary Ellen Henderson tiene solo
contexto municipal y 70 escuelas permanecen como puntos sin polígono asignado.

## Scores y colores

Los 192 scores provienen del archivo
`middle_schools_greatschools_DC_area.xlsx` entregado por el usuario. El proyecto
no contiene automatización para extraerlos de GreatSchools. La copia original,
su SHA-256 y una evidencia por fila se conservan de forma auditable. El Excel
original no se incluye en el sitio publicado; solo se publica la metadata de
evidencia necesaria para interpretar cada score.

| Score | Color |
|---:|---|
| 9–10 | Verde intenso `#1a9850` |
| 7–8 | Verde `#91cf60` |
| 5–6 | Amarillo `#fee08b` |
| 3–4 | Naranja `#fc8d59` |
| 1–2 | Rojo intenso `#d73027` |
| Sin dato | Gris `#727a80` |

## Zonas y escuelas charter

Una ubicación escolar no implica que exista una zona residencial. Las charter,
programas de elección y algunos campus combinados permanecen visibles como
puntos y se etiquetan sin zona propia. Los límites municipales, como Falls
Church City, se muestran solo como contexto y nunca como zona de asistencia.

El navegador no realiza matching aproximado. Cada polígono se resuelve por su
nombre de fuente, jurisdicción e ID estable mediante
`data/boundary-crosswalk.json`.

| Jurisdicción | Capa | Vigencia declarada |
|---|---|---|
| Arlington | Zonas de middle school | 2022–2023; metadata oficial atrasada |
| Fairfax | Zonas de middle school | 2025–2026; histórica tras cambios 2026–2027 |
| Falls Church City | Límite municipal | Contexto actual, no zona escolar |
| Alexandria | Zonas de middle school | 2026–2027 |
| Montgomery | Zonas de middle school | 2026–2027 |
| Prince George's | Zonas de middle school | 2026–2027 |
| Washington, DC | Zonas de middle school | Servicio oficial sin año publicado |

## Contratos y controles

- `data/schools.json`: 192 identidades, tipo, grados y score.
- `data/school-locations.json`: direcciones, coordenadas y fuente oficial.
- `data/rating-evidence.json`: trazabilidad del libro y evidencia individual.
- `data/boundary-manifest.json`: fuente, vigencia y semántica de cada capa.
- `data/boundary-crosswalk.json`: asociaciones explícitas feature–escuela.
- `data/source-snapshot.json`: conteos, fechas y hashes de cartografía.

Consulte [metodología](docs/METHODOLOGY.md) y
[diccionario de datos](docs/DATA_DICTIONARY.md) para el detalle técnico.

## Limitaciones

- Los años escolares de las capas pueden diferir entre jurisdicciones.
- Un score único no resume por sí solo la calidad de una escuela.
- El mapa no confirma elegibilidad, admisión ni asignación de una dirección.
- Las fuentes oficiales pueden cambiar después de la fecha del snapshot.

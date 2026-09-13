# Elementary schools del área de Washington, DC

[Abrir el mapa de elementary schools](https://jp1309.github.io/highschools-dc-metro/elementary-schools/) ·
[Abrir el mapa de middle schools](https://jp1309.github.io/highschools-dc-metro/middle-schools/) ·
[Abrir el mapa de high schools](https://jp1309.github.io/highschools-dc-metro/)

Explorador independiente de 552 escuelas públicas y charter en siete
jurisdicciones del área metropolitana. El mapa combina scores 1–10 entregados
por el usuario, ubicaciones documentadas y zonas de asistencia solo cuando hay
una relación explícita y verificable.

## Universo

El universo reproduce exactamente las 552 filas calificadas del libro fuente
`elementary_schools_greatschools_DC_area.xlsx`: 492 escuelas públicas de
distrito y 60 charter públicas. Incluye escuelas cuyo rango declarado contiene
al menos un grado de elementary, aunque también atiendan pre-K, middle o high
school.

No se presenta como un censo completo de todas las escuelas de la región. Es la
materialización trazable de las fichas revisadas y calificadas en el libro
entregado por el usuario.

| Jurisdicción | Escuelas |
|---|---:|
| Alexandria City, VA | 14 |
| Arlington, VA | 25 |
| Fairfax County, VA | 134 |
| Falls Church City, VA | 2 |
| Montgomery County, MD | 126 |
| Prince George's County, MD | 121 |
| Washington, DC | 130 |
| **Total** | **552** |

## Scores y colores

El proyecto no extrae scores automáticamente de GreatSchools. Conserva una
copia del libro fuente, su SHA-256 y evidencia por fila. El Excel no se incluye
en el artefacto publicado en GitHub Pages.

| Score | Color |
|---:|---|
| 9–10 | Verde intenso `#1a9850` |
| 7–8 | Verde `#91cf60` |
| 5–6 | Amarillo `#fee08b` |
| 3–4 | Naranja `#fc8d59` |
| 1–2 | Rojo intenso `#d73027` |
| Sin dato | Gris `#727a80` |

## Zonas y controles

Las ubicaciones y las zonas son capas independientes: cualquiera puede
ocultarse sin afectar a la otra. Las charter, programas de elección y campus
sin zona residencial permanecen visibles como puntos. Un límite municipal se
etiqueta como contexto y nunca se presenta como zona de asistencia.

El navegador no hace matching aproximado por nombre. Las asociaciones entre
polígonos y escuelas se resuelven mediante IDs estables y jurisdicción en
`data/boundary-crosswalk.json`.

## Contratos publicados

- `data/schools.json`: identidades, tipo, grados y score.
- `data/school-locations.json`: direcciones, coordenadas y fuente.
- `data/rating-evidence.json`: trazabilidad del libro y evidencia individual.
- `data/boundary-manifest.json`: fuente, vigencia y semántica de cada capa.
- `data/boundary-crosswalk.json`: asociaciones explícitas feature–escuela.
- `data/source-snapshot.json`: conteos, fechas y hashes de cartografía.

## Limitaciones

- Un score único no resume por sí solo la calidad de una escuela.
- Los años escolares de las capas pueden diferir entre jurisdicciones.
- El mapa no confirma elegibilidad, admisión ni asignación de una dirección.
- Las fuentes oficiales pueden cambiar después de la fecha del snapshot.

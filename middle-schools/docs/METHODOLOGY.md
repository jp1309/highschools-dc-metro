# Metodología de middle schools

## Separación del proyecto

Este subproyecto se publica bajo `middle-schools/` y no lee datos, manifiestos
ni GeoJSON del mapa de high schools. Comparte patrones de diseño y validación,
pero no identidades, ratings ni correspondencias geográficas.

## Universo escolar

La unidad de análisis es cada una de las 192 filas calificadas del libro
entregado el 30 de agosto de 2026. Se conserva el alcance del usuario, incluidos
rangos K–8, 5–8, 6–12 y similares cuando atienden 6.º, 7.º u 8.º. El nombre no
es una llave: el ID combina jurisdicción y nombre normalizado, mientras que el
ID de GreatSchools se almacena con su estado porque el número aislado no es
globalmente único.

La selección no es un censo. No se incorporan por cuenta propia escuelas fuera
del libro ni se asignan scores estimados a registros ausentes.

## Scores

El score publicado es el valor entero 1–10 de la fila correspondiente. La
procedencia se marca `user_supplied_workbook`; `rating_as_of` queda
en `null` porque el libro no declara la vigencia propia de cada score, y
`rating_checked_at` registra la fecha de entrega/procesamiento. El pipeline no
visita ni extrae automáticamente páginas de GreatSchools.

## Ubicaciones

Las direcciones y coordenadas se materializan desde capas o directorios
oficiales. Los cruces se hacen dentro de cada jurisdicción y las diferencias de
nombre se documentan como aliases. Las ubicaciones se conservan separadas de
los scores en `data/school-locations.json`. Un registro sin ubicación
verificable hace fallar la publicación; no se usan centroides o coordenadas
inventadas.

## Límites

Cada archivo GeoJSON tiene fuente, fecha de consulta, año escolar declarado,
conteo y hash. El crosswalk relaciona exactamente `path + feature_name` con un
ID escolar. No se usa matching difuso en el navegador.

`attendance_boundary` significa zona oficial publicada por la autoridad.
`municipal_boundary` es solo contexto administrativo. Las charter y programas
de elección no reciben un polígono residencial por aproximación.

## Actualizaciones seguras

Una actualización debe ser completa y fail-closed: un error HTTP, un cambio de
esquema, un conteo inesperado, un ID ambiguo o una cobertura parcial termina el
proceso antes de reemplazar los JSON publicados. Después se ejecutan el
validador, las pruebas, la revisión sintáctica de JavaScript y la construcción
del único artifact de GitHub Pages.

# High Schools del área de Washington, DC

[Ver el mapa publicado](https://jp1309.github.io/highschools-dc-metro/) ·
[Estado de validación](https://github.com/jp1309/highschools-dc-metro/actions/workflows/validate.yml)

Mapa estático para explorar 84 high schools públicas y las capas geográficas
disponibles en siete jurisdicciones del área de Washington, DC. Combina puntos
de escuelas, calificaciones declaradas y boundaries publicados por autoridades
locales o conservados como snapshots del repositorio.

El mapa es una herramienta exploratoria. **No confirma la escuela asignada a
una dirección, no garantiza elegibilidad de matrícula y no debe usarse como
única base para decisiones de vivienda.** Verifique siempre con el distrito
escolar correspondiente.

## Qué mejoró esta versión

- separa HTML, estilos, lógica y datos;
- usa IDs estables y una unión explícita por crosswalk, sin coincidencias
  parciales de nombres durante la carga;
- distingue zonas de asistencia de límites municipales;
- no fabrica polígonos para escuelas sin boundary confirmado;
- muestra fuente, vigencia y limitaciones en la interfaz;
- valida contratos, geometrías, referencias y jurisdicciones antes de publicar;
- incluye un proceso controlado para comprobar y actualizar fuentes oficiales.

## Alcance actual

`data/schools.json` contiene 84 escuelas:

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

Este universo es una selección heredada del repositorio original, no una lista
completa de todas las high schools del área metropolitana. No incluye, por
ejemplo, todos los distritos que forman parte de la región. Las escuelas magnet,
charter, alternativas o sin attendance zone tradicional requieren un tratamiento
específico y pueden estar ausentes.

El crosswalk actual cubre 85 features: 84 asociaciones explícitas y una feature
de Centreville conservada como no asociada porque no existe un registro de esa
escuela en `schools.json`. Dos asociaciones —Alexandria City High School y
Meridian High School— usan límites municipales, no zonas de asistencia. En
términos estrictos, 82 de las 84 escuelas tienen una zona oficial de asistencia;
las otras dos tienen contexto municipal oficial.

## Fuentes geográficas y vigencia

| Capa publicada | Features | Vigencia declarada | Tipo | Estado de actualización |
|---|---:|---|---|---|
| Fairfax County, VA | 24 | 2025–2026 | zona de asistencia | endpoint oficial configurado |
| Montgomery County, MD | 25 | 2026–2027 | zona de asistencia | endpoint oficial verificado y snapshot actualizado |
| Arlington, VA | 3 | 2022–2023 | zona de asistencia | snapshot; endpoint autoritativo pendiente |
| Prince George's County, MD | 21 | desconocida | zona de asistencia | snapshot; procedencia/vigencia pendiente |
| Alexandria City, VA | 1 | desconocida | **límite municipal** | snapshot; no es attendance boundary |
| Falls Church City, VA | 1 | no aplica | **límite municipal** | endpoint oficial configurado; filtro FIPS 51610 |
| Washington, DC | 10 | no indicada en la capa | zona de asistencia | endpoint oficial configurado |

Las fuentes verificadas para actualización están declaradas en
`config/sources.json`:

- Fairfax County GIS, `OpenData_S1/FeatureServer/12`;
- Montgomery County GeoHub / MCPS,
  `MCPS_High_School_Areas/FeatureServer/0`;
- DC GIS Open Data, `Education_WebMercator/MapServer/15`.
- City of Falls Church GIS / VGIN,
  `Jurisdictional_Boundary/FeatureServer/0`, filtrado por `STCOFIPS=51610`.

Una URL accesible o una respuesta HTTP 200 no prueba vigencia. El proceso exige
el conteo esperado, nombres únicos y, donde existe, el año escolar esperado.
Arlington, Prince George's y Alexandria permanecen deshabilitados para refresh
automático hasta verificar una fuente autoritativa adecuada. Falls Church está
habilitado, pero se publica como contexto municipal y nunca como zona escolar.

## Estado y actualización de las calificaciones

Las 84 calificaciones actuales proceden del libro
`lista_84_escuelas_greatschools.xlsx` proporcionado por el usuario. La entrega
incluye `school_id`, URL individual, score 1–10, fecha de consulta y estado
verificado para cada escuela. La actualización del 30 de agosto de 2026 cubre
84 de 84 escuelas; su hash y la evidencia fila por fila se conservan en
`data/rating-evidence.json`. El archivo original exacto queda preservado en
`outputs/ratings-manual-20260830/lista_84_escuelas_greatschools.xlsx` y el
validador comprueba su SHA-256 antes de publicar.

Los [Términos de uso de GreatSchools](https://www.greatschools.org/gk/terms/)
prohíben el web scraping, harvesting y extraction. Este proyecto no visita ni
extrae automáticamente páginas de GreatSchools. Un refresh solo puede usar una
API, feed o exportación entregada con autorización y dentro del alcance de la
licencia correspondiente. La disponibilidad de una API no concede por sí sola
derecho a reutilizar o redistribuir sus datos.

El contrato distingue tres estados:

- `verified`: rating 1–10 respaldado por evidencia completa de una entrega
  autorizada o una verificación manual proporcionada por el usuario;
- `not_available`: la entrega autorizada cubrió la escuela, pero no proporcionó
  un rating; se publica `rating: null`;
- `legacy_unverified`: valor heredado sin evidencia por escuela.

La escala visual usa cinco rangos consistentes en puntos y límites: 9–10 verde
intenso (`#1a9850`), 7–8 verde (`#91cf60`), 5–6 amarillo (`#fee08b`), 3–4
naranja (`#fc8d59`) y 1–2 rojo intenso (`#d73027`). El gris (`#727a80`) queda
reservado para una escuela sin rating. Los límites municipales conservan el
color del score y se diferencian mediante un borde discontinuo.

`scripts/import_authorized_ratings.py` materializa una entrega autorizada. El
script no aplica cambios salvo que se use `--apply`, se confirme explícitamente
la licencia con `--license-confirmed` y la entrega cubra exactamente las 84
escuelas. Un bloqueo, error de red, error de parseo o identidad ambigua no se
convierte en `not_available`: el refresh falla y conserva intactos los datos
publicados.

Cada actualización aceptada escribe `data/rating-evidence.json`, con una
referencia individual desde cada escuela. `rating_as_of` conserva únicamente el
año o mes que declare la fuente (`YYYY`, `YYYY-MM` o `null`); no se inventa un
mes. `rating_checked_at` registra por separado el instante UTC en que se procesó
la entrega.

El método de esta actualización es `user_supplied_manual_verification`: el
pipeline no visitó las fichas ni extrajo scores; materializó y validó el libro
entregado por el usuario. Este método se mantiene separado de
`authorized_bulk_feed` para no confundir su procedencia.

## Arquitectura de datos

```text
fuentes GIS oficiales/snapshots       ratings con procedencia documentada
              |                                  |
              v                                  v
     GeoJSON en la raíz           feed autorizado o tabla del usuario
              |                                  |
              v                                  v
 data/boundary-manifest.json      data/rating-evidence.json
              |                                  |
 data/boundary-crosswalk.json     data/schools.json
              |                                  |
              +---------------+------------------+
                              v
                    scripts/validate_data.py
                              |
                              v
                   index.html + assets/app.js
```

- `data/schools.json`: escuela, punto y estado materializado de su calificación.
- `data/rating-evidence.json`: evidencia individual de una entrega autorizada
  o tabla manual proporcionada por el usuario que respalda los ratings.
- `data/boundary-manifest.json`: archivo, jurisdicción, campo de nombre,
  vigencia y tipo de cada capa.
- `data/boundary-crosswalk.json`: relación feature → `school_id`, o estado no
  asociado con una razón.
- `config/sources.json`: endpoints y expectativas para un refresh controlado.
- `config/rating-sources.json`: fuentes, métodos y condiciones autorizadas para
  importar ratings; no contiene credenciales.
- `scripts/refresh_boundaries.py`: descarga y valida todas las fuentes
  habilitadas antes de reemplazar archivos; sin `--apply` solo comprueba.
- `scripts/import_authorized_ratings.py`: valida y materializa únicamente feeds
  o exports autorizados con cobertura completa.
- `scripts/validate_data.py`: puerta de calidad para los artefactos publicados.
- `tests/`: pruebas de regresión con `unittest`.

Consulte [el diccionario de datos](docs/DATA_DICTIONARY.md) y
[la metodología](docs/METHODOLOGY.md) para los contratos y decisiones de
procedencia.

## Ejecución local

Requisitos: Python 3 y un navegador moderno. No hay dependencias Python de
terceros para validar ni servir el proyecto.

En PowerShell:

```powershell
git clone https://github.com/jp1309/highschools-dc-metro.git
cd highschools-dc-metro
py -3 scripts/validate_data.py
py -3 -m unittest discover -s tests -v
py -3 -m http.server 8000
```

Abra `http://localhost:8000/`. El sitio usa `fetch()` y debe servirse por HTTP;
abrir `index.html` mediante `file://` no es una prueba válida.

En Linux o macOS, sustituya `py -3` por `python3`.

## Validación

La validación comprueba, entre otras reglas:

- esquema, tipos, IDs únicos y campos obligatorios de escuelas;
- calificaciones, estados y coordenadas dentro de rangos válidos;
- coherencia entre rating, URL, vigencia, fecha de consulta, método y evidencia;
- cobertura completa y referencias uno-a-uno de la evidencia de ratings;
- existencia, estructura y geometrías básicas de cada GeoJSON declarado;
- cobertura exacta del crosswalk sobre las features publicadas;
- referencias a IDs existentes y consistencia de jurisdicción;
- razones explícitas para features no asociadas.

Ejecute siempre:

```powershell
py -3 scripts/validate_data.py
py -3 -m unittest discover -s tests -v
git diff --check
```

GitHub Actions repite la validación, las pruebas y la construcción del artifact
estático en cada push y pull request.

### Importar ratings autorizados

Obtenga primero una API, feed o exportación cuya licencia permita expresamente
este uso y revise las opciones del importador:

```powershell
py -3 scripts/import_authorized_ratings.py --help
py -3 scripts/import_authorized_ratings.py --input C:\secure\authorized-ratings.csv
```

La segunda orden es una vista previa y no escribe. Solo después de revisar que
las 84 escuelas están resueltas, aplique la misma entrega:

```powershell
py -3 scripts/import_authorized_ratings.py --input C:\secure\authorized-ratings.csv --apply --license-confirmed
py -3 scripts/validate_data.py
py -3 -m unittest discover -s tests -v
```

Ambos flags son necesarios; la confirmación declara que el operador verificó la
licencia, no sustituye esa verificación.

## Actualizar boundaries

Primero compruebe las fuentes habilitadas sin modificar el repositorio:

```powershell
py -3 scripts/refresh_boundaries.py
```

Revise conteos, años y cambios esperados. Para aplicar todas las descargas
validadas:

```powershell
py -3 scripts/refresh_boundaries.py --apply
py -3 scripts/validate_data.py
py -3 -m unittest discover -s tests -v
```

`--apply` reemplaza los archivos habilitados solo después de que todas las
descargas superen sus controles y escribe evidencia de la comprobación en
`data/source-snapshot.json`. Si cambian nombres o features, actualice el
manifiesto y el crosswalk de forma explícita; nunca añada matching difuso al
frontend.

## Publicación

El repositorio publica mediante GitHub Actions. `.github/workflows/pages.yml`
valida el repositorio, ejecuta las pruebas, genera `_site` y despliega el
artifact oficial de Pages. El workflow `Validate` repite los controles en cada
push y pull request.

El despliegue se detiene si falla el validador o cualquier prueba.

## Limitaciones conocidas

- La cobertura geográfica y escolar no equivale a toda la región metropolitana.
- Las 84 calificaciones tienen URL individual y evidencia de la entrega manual
  proporcionada por el usuario, fechada el 30 de agosto de 2026.
- Las capas tienen vigencias diferentes; tres continúan como snapshots sin
  refresh autoritativo confirmado.
- Alexandria y Falls Church muestran contexto municipal, no asignación escolar.
- Un punto de escuela puede estar desactualizado o fuera de la zona que el
  usuario espera; no demuestra asignación de una dirección.
- La validación prueba consistencia interna, no certifica la actualidad de una
  autoridad externa.
- Los GeoJSON de origen son grandes; la optimización geométrica sigue pendiente
  y debe preservar una copia auditable de la fuente.

## Contribuir y licencias

Lea [CONTRIBUTING.md](CONTRIBUTING.md) antes de modificar datos o fuentes.

El código se distribuye bajo la [licencia MIT](LICENSE). Los GeoJSON,
calificaciones, nombres, marcas y otros datos externos **no quedan relicenciados
por MIT**: conservan los términos, licencias y requisitos de atribución de sus
respectivos proveedores. Verifique esos términos antes de reutilizar o
redistribuir los datos.

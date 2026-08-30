# Diccionario de datos

Este documento describe los contratos materializados que consume el frontend.
Los JSON se versionan junto con el código y deben pasar
`scripts/validate_data.py` antes de publicarse.

## `data/schools.json`

Arreglo de escuelas. Cada objeto representa una escuela, no una zona de
asistencia.

| Campo | Tipo | Requerido | Descripción |
|---|---|---:|---|
| `id` | string | sí | Identificador estable y único usado en las relaciones internas. |
| `name` | string | sí | Nombre público de la escuela. |
| `address` | string | sí | Dirección mostrada al usuario. No se usa como identificador. |
| `rating` | integer/null | sí | Calificación entre 1 y 10, o `null` cuando una entrega con procedencia documentada indica que no está disponible. |
| `lat` | number | sí | Latitud WGS84 del punto de la escuela. |
| `lng` | number | sí | Longitud WGS84 del punto de la escuela. |
| `jurisdiction` | string | sí | Jurisdicción administrativa normalizada. |
| `rating_status` | string | sí | `verified`, `not_available` o `legacy_unverified`. |
| `rating_source` | string | sí | Nombre de la fuente declarada. |
| `rating_source_url` | string/null | sí | URL HTTPS del recurso documentado que cubre la escuela; `null` únicamente para el legado sin evidencia. |
| `rating_source_school_id` | string/null | sí | ID estable asignado por la fuente; es obligatorio en una entrega autorizada o manual verificada y `null` para el legado. |
| `rating_as_of` | string/null | sí | Año (`YYYY`) o mes (`YYYY-MM`) efectivo declarado por la fuente. No se infiere de la fecha de consulta. |
| `rating_checked_at` | string/null | sí | Instante RFC 3339 UTC en que se procesó la entrega; `null` para el legado sin evidencia. |
| `rating_method` | string | sí | `authorized_bulk_feed`, `user_supplied_manual_verification` o `legacy_transcription`. |
| `rating_evidence_id` | string/null | sí | Identificador de evidencia que respalda el estado; `null` para el legado sin evidencia. |
| `provenance_note` | string | sí | Nota honesta sobre procedencia, método o limitaciones del registro. |

Las coordenadas representan ubicaciones puntuales. No deben calcularse a partir
del centro del rectángulo de un boundary.

### Reglas condicionales de ratings

- `verified` exige `rating` 1–10, URL de fuente, fecha de consulta, método
  admitido y un `rating_evidence_id` existente.
- `not_available` exige `rating: null`, pero también URL, fecha de consulta,
  método admitido y evidencia. Significa que la entrega cubrió la escuela y
  no proporcionó un rating; no representa un fallo técnico.
- `legacy_unverified` identifica exclusivamente valores migrados sin evidencia
  por escuela. Usa `legacy_transcription`; URL, fecha de consulta, ID de fuente
  y evidencia son `null`.
- `rating_as_of` puede ser `null` si la fuente no declara vigencia. La fecha de
  procesamiento nunca debe copiarse a este campo.
- Un error de descarga, autorización, parseo o identidad impide materializar la
  actualización. No se codifica como `not_available` y no reemplaza datos
  existentes.

## `data/rating-evidence.json`

Registro de evidencia de una entrega autorizada o proporcionada manualmente por
el usuario. Debe permitir reconstruir qué se recibió, cuándo se procesó y cómo
se resolvió cada una de las 84 escuelas sin guardar secretos.

El objeto raíz contiene `schema_version`, la descripción `legacy_dataset` y un
arreglo `runs`. Cada ejecución publicada contiene:

- `run_id`: identificador único de la ejecución;
- `completed_at`: último instante de consulta de la entrega;
- `source`: nombre del proveedor;
- `method`: `authorized_bulk_feed` o `user_supplied_manual_verification`;
- `source_workbook`: nombre, ruta relativa versionada, SHA-256 y origen del
  libro cuando el usuario proporciona la tabla; el hash debe coincidir con los
  bytes del archivo preservado;
- `coverage`: número de escuelas cubiertas, que debe ser 84;
- `attempts`: arreglo con una entrada terminal por escuela.

Cada entrada de `attempts` contiene:

- `evidence_id` único, referenciado por `schools[].rating_evidence_id`;
- `school_id` existente en `data/schools.json`;
- `rating_source`, URL individual e ID de la fuente;
- `rating_status` terminal (`verified` o `not_available`);
- `rating`, `rating_as_of` y `rating_method` recibidos;
- `rating_checked_at`;
- `outcome`, que debe coincidir con `rating_status`.

La referencia debe ser uno-a-uno: toda escuela `verified` o `not_available`
apunta a exactamente una evidencia de la ejecución publicada y los valores de
ambos archivos deben coincidir. Una ejecución aplicable cubre 84 de 84 escuelas.
El archivo no debe contener tokens de API, cookies, credenciales ni respuestas
crudas cuya redistribución no permita la licencia.

## `config/rating-sources.json`

Declara fuentes de ratings admitidas, métodos autorizados, escala y reglas de
validación. No autoriza por sí mismo el uso de datos y no almacena credenciales.
El importador exige además `--license-confirmed` al aplicar un cambio.

## Escala visual de ratings

| Rating | Categoría | Color |
|---:|---|---|
| 9–10 | `best` | verde intenso `#1a9850` |
| 7–8 | `good` | verde `#91cf60` |
| 5–6 | `mid` | amarillo `#fee08b` |
| 3–4 | `low` | naranja `#fc8d59` |
| 1–2 | `worst` | rojo intenso `#d73027` |
| `null` | `none` | gris `#727a80` |

El frontend aplica la misma categoría a puntos y polígonos asociados. El tipo
de boundary se comunica mediante opacidad y patrón de borde, no alterando el
color derivado del rating.

## `data/boundary-manifest.json`

Inventario de las capas de límites usadas por el mapa. Permite separar la
vigencia y naturaleza de cada fuente de la lista de escuelas.

Es un arreglo con una entrada por capa. Cada entrada incluye:

| Campo | Tipo | Requerido | Descripción |
|---|---|---:|---|
| `path` | string | sí | Ruta relativa al GeoJSON versionado. |
| `jurisdiction` | string | sí | Jurisdicción a la que pertenece la capa. |
| `source_name` | string | sí | Autoridad o descripción honesta del snapshot publicado. |
| `source_url` | string/null | sí | URL autoritativa verificada, o `null` cuando sigue pendiente. |
| `name_field` | string | sí | Propiedad de cada feature que contiene el nombre original. |
| `school_year` | string | sí | Año escolar `YYYY-YYYY` declarado por la fuente o `unknown`. |
| `boundary_type` | string | sí | `attendance_boundary` o `municipal_boundary`. |

Una respuesta HTTP exitosa no demuestra actualidad. La vigencia debe provenir
del contenido o metadatos oficiales de la capa.

Cuando una fuente requiere seleccionar una jurisdicción dentro de una capa más
amplia, `config/sources.json` puede declarar un filtro ArcGIS `where`. El refresh
registra ese filtro junto con la URL, el hash y el conteo para impedir que una
consulta sin filtrar sustituya silenciosamente el snapshot publicado.

## `data/boundary-crosswalk.json`

Relación explícita entre cada feature de las capas declaradas en el manifiesto
y `schools.json`. Sustituye las coincidencias parciales de nombres en tiempo de
ejecución.

Es un arreglo con objetos `path` y `mappings`. Cada mapping identifica una
feature por su nombre original y contiene:

- `feature_name`: valor exacto del `name_field` de la feature;
- `status`: `matched` o `unmatched`;
- `school_id`: ID existente en `schools.json` cuando `status` es `matched`, o
  `null` cuando es `unmatched`;
- `reason`: explicación obligatoria cuando `status` es `unmatched`.

Las entradas no deben cruzar jurisdicciones. Un boundary sin asociación no
recibe una calificación predeterminada ni genera una zona aproximada.

## GeoJSON

Los GeoJSON conservan los nombres y geometrías proporcionados por sus fuentes.
El CRS esperado para el navegador es WGS84 (`EPSG:4326`) y las geometrías deben
ser `Polygon` o `MultiPolygon` válidos. El manifiesto y el crosswalk son la capa
de normalización; no se deben reescribir silenciosamente los nombres originales
dentro del GeoJSON.

## Convenciones de ausencia

- Use `unknown` únicamente donde el contrato lo admite, como una vigencia no
  confirmada en el manifiesto.
- Use una explicación explícita para una feature no asociada.
- No use `0`, cadenas vacías, calificaciones medias ni coordenadas inventadas
  como sustitutos de valores desconocidos.

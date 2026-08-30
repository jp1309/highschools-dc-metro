# Diccionario de datos de middle schools

## `data/schools.json`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | string | ID estable y único, con jurisdicción. |
| `source_row_number` | integer | Número de fila del registro en el libro. |
| `name` | string | Nombre mostrado. |
| `city` | string | Ciudad normalizada. |
| `jurisdiction` | string | Una de las siete jurisdicciones del proyecto. |
| `school_type` | string | `public` o `charter`, según el libro. |
| `grades_label` | string | Rango original de grados. |
| `grades_served` | array[integer] | Grados materializados; `-1` es PK y `0` es K. |
| `attendance_model` | string | `zoned`, `charter_no_zone`, `choice_no_zone`, `municipal_context` o `unknown`. |
| `district` | string/null | Texto original; `-` se materializa como `null`. |
| `rating` | integer | Score 1–10 entregado por el usuario. |
| `rating_status` | string | `verified_user_supplied` para esta entrega completa. |
| `rating_source_url` | string | URL individual contenida en el libro. |
| `rating_source_school_id` | string | Clave estado + ID del proveedor. |
| `rating_as_of` | null/string | Vigencia declarada por la fuente; desconocida en esta entrega. |
| `rating_checked_at` | string | Fecha UTC de procesamiento. |
| `rating_evidence_id` | string | Enlace lógico a la evidencia individual. |

## `data/school-locations.json`

Contiene una fila por `school_id` con `address`, `lat`, `lng`,
`location_status`, `source_name`, `source_url`, `retrieved_at` y `note`. Solo
`verified_official` puede aportar coordenadas al mapa; un registro pendiente
mantiene esos campos en `null` y no puede superar el gate de publicación.

## `data/boundary-manifest.json`

Cada entrada declara `path`, `jurisdiction`, `source_name`, `source_url`,
`name_field`, `school_year` y `boundary_type`. Las rutas son internas a este
subproyecto y no pueden contener `..`.

## `data/boundary-crosswalk.json`

Cada archivo contiene `mappings` con `feature_name`, `status`, `school_id` y,
para objetos no asociados, `reason`. La unión siempre usa el nombre exacto del
campo indicado por el manifiesto.

## `data/rating-evidence.json`

Registra el nombre, ruta privada dentro del repositorio, SHA-256 y cobertura del
workbook, además de una evidencia por escuela. El archivo Excel no forma parte
del artifact web.

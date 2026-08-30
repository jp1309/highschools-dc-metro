# Metodología y procedencia

## Propósito

El proyecto combina una lista curada de high schools públicas con capas
geográficas de distintas jurisdicciones del área de Washington, DC. Sirve para
explorar espacialmente calificaciones publicadas y cobertura geográfica; no
determina elegibilidad de matrícula ni sustituye la confirmación con el distrito
escolar.

## Flujo de datos

```text
 fuentes GIS oficiales/snapshots       ratings con procedencia documentada
              |                                  |
              v                                  v
      GeoJSON originales          feed autorizado o tabla del usuario
              |                                  |
              v                                  v
 data/boundary-manifest.json      data/rating-evidence.json
              |                                  |
 data/boundary-crosswalk.json     data/schools.json
              |                                  |
              +---------------+------------------+
                              v
                   validación automatizada
                              |
                              v
                 index.html + assets/app.js
```

Los GeoJSON se conservan como evidencia de la capa descargada. El manifiesto
declara qué archivo se publica, su jurisdicción, campo de nombre, vigencia y
tipo. El crosswalk resuelve cada nombre original a un ID de escuela o documenta
por qué no existe asociación. El frontend consume estos artefactos; no realiza
uniones difusas.

## Calificaciones y escuelas

Las calificaciones presentes en la versión original carecían de URL y evidencia
individual y se conservaron inicialmente como `legacy_unverified`. El 30 de
agosto de 2026 el usuario proporcionó un libro completo con 84 IDs, 84 URLs
individuales, 84 scores válidos y fecha de consulta común. Esa entrega reemplazó
el legado y ahora los 84 registros tienen `rating_status: verified` y método
`user_supplied_manual_verification`.

Las escuelas se identifican mediante `id`. Nombre, dirección y coordenadas son
atributos. El rating es un atributo temporal y debe vincularse a una fuente y a
una evidencia individual, no únicamente al nombre de la escuela.

### Restricción de GreatSchools

Los [Términos de uso de GreatSchools](https://www.greatschools.org/gk/terms/),
actualizados el 27 de febrero de 2026, prohíben cualquier forma de web scraping,
web harvesting y web extraction, así como herramientas automatizadas sin
permiso. En consecuencia, este proyecto no implementa scraping de páginas ni
usa navegación automatizada para construir ratings.

Un refresh automatizado solo puede usar una API, feed o exportación
proporcionada con autorización y utilizada dentro de los términos contratados.
Las condiciones específicas del servicio también pueden limitar exposición,
atribución, combinación o redistribución. `--license-confirmed` registra que el
operador revisó esas condiciones; no concede una licencia ni reemplaza su texto.

También puede materializarse una tabla ya recopilada y proporcionada por el
usuario. En ese caso el repositorio no consulta la web: valida cobertura,
identidad, URLs, escala, fechas y unicidad, registra el hash del libro de entrada
y usa el método `user_supplied_manual_verification`. El libro recibido se
preserva en `outputs/` y el validador comprueba que sus bytes coincidan con el
SHA-256 declarado en la evidencia.

### Escala cromática

La calificación se representa en cinco rangos fijos: 9–10 verde intenso
(`#1a9850`), 7–8 verde (`#91cf60`), 5–6 amarillo (`#fee08b`), 3–4 naranja
(`#fc8d59`) y 1–2 rojo intenso (`#d73027`). El gris (`#727a80`) se reserva para
registros sin rating. Los límites municipales conservan el color del rating y
se distinguen por borde discontinuo; no cambian de categoría al pasar el mouse.

### Importación y evidencia

`scripts/import_authorized_ratings.py` procesa una entrega autorizada de manera
fail-closed. Antes de escribir exige:

1. fuente y método admitidos por `config/rating-sources.json`;
2. confirmación explícita `--license-confirmed`;
3. resolución inequívoca de las 84 escuelas mediante IDs estables;
4. rating 1–10 o resultado explícito `not_available` para cada escuela;
5. URL, instante UTC, método y evidencia individual completos;
6. ausencia de duplicados, escuelas extra y resultados parciales.

El modo sin `--apply` valida sin sustituir archivos publicados. Con `--apply`,
los cambios a `data/schools.json` y `data/rating-evidence.json` se aceptan solo
después de superar el conjunto completo de controles.

Un rating `verified` conserva el valor entregado. `not_available` significa que
la fuente autorizada cubrió la escuela pero no suministró un rating y, por ello,
materializa `rating: null`. Un bloqueo, error de red, error de parseo o identidad
ambigua es un fallo del refresh, no evidencia de ausencia; no modifica los datos
publicados.

`rating_as_of` representa exclusivamente la vigencia que declara la fuente y
puede contener `YYYY`, `YYYY-MM` o `null`. No se inventa un mes cuando solo se
conoce el año. `rating_checked_at` conserva separadamente el instante RFC 3339
UTC en que se procesó la entrega.

## Límites geográficos

Las capas no comparten necesariamente la misma vigencia. El valor
`school_year` del manifiesto se toma de los metadatos o del nombre de la fuente;
cuando no puede confirmarse se mantiene como desconocido. Tampoco todas las
geometrías representan lo mismo: una zona de asistencia escolar y un límite
municipal deben etiquetarse de manera diferente.

El proyecto no crea polígonos aleatorios para escuelas sin boundary. En esos
casos muestra únicamente el punto conocido y comunica la ausencia de una zona
confirmada.

Falls Church City es un caso de contexto municipal: Meridian High School es la
única high school del sistema, pero la capa publicada no se presenta como una
zona de asistencia. El pipeline descarga el límite jurisdiccional oficial y lo
filtra de forma reproducible por `STCOFIPS='51610'`; el filtro y la URL quedan
registrados en `data/source-snapshot.json`.

## Asociación entre capas y escuelas

La asociación se materializa en `data/boundary-crosswalk.json`. Se revisa con
el nombre original, jurisdicción y contexto de la fuente. No se aceptan
coincidencias por subcadenas globales: dos escuelas de jurisdicciones diferentes
pueden tener nombres parecidos o idénticos.

Una feature que no corresponde al alcance —por ejemplo, una middle school, una
escuela sin zona tradicional o una geometría no escolar— permanece sin asociar
y conserva una razón. Esto evita ocultarla o colorearla con una calificación
incorrecta.

## Validación

La validación automática comprueba los contratos de los datos materializados,
unicidad de IDs, rangos de coordenadas y calificaciones, estados de ratings,
referencias uno-a-uno a evidencia, cobertura 84/84, referencias del crosswalk,
consistencia jurisdiccional y existencia/estructura básica de las capas
declaradas. Las pruebas de regresión complementan estas reglas.

Estas comprobaciones detectan inconsistencias internas, pero no certifican que
una fuente externa continúe vigente ni que una dirección determine la escuela
asignada. La actualidad debe verificarse contra la autoridad correspondiente en
cada actualización.

## Uso responsable

- Confirme la asignación escolar con el distrito antes de tomar decisiones de
  vivienda o matrícula.
- No interprete una calificación única como una medición completa de calidad.
- Distinga ratings `legacy_unverified` de observaciones `verified`; conservar un
  valor heredado no demuestra que siga vigente.
- Compare años escolares únicamente cuando la metodología y cobertura sean
  compatibles.
- Trate los puntos y boundaries como ayudas cartográficas, no como asesoría
  legal o garantía de admisión.

## Licencias y atribución

El código del repositorio se distribuye bajo MIT. Los datos externos y marcas
no quedan relicenciados por `LICENSE`: cada GeoJSON, calificación y fuente
conserva los términos, licencias y requisitos de atribución de su proveedor.
Quien redistribuya o actualice datos debe revisar esos términos directamente.

# Contribuir

Gracias por ayudar a mejorar el mapa. El objetivo principal del repositorio es
que cada dato publicado sea trazable y que una actualización incorrecta no
llegue al sitio.

## Preparar el entorno

Solo se necesita Python 3 y un navegador moderno. El validador y las pruebas
usan exclusivamente la biblioteca estándar de Python.

```powershell
git clone https://github.com/jp1309/highschools-dc-metro.git
cd highschools-dc-metro
py -3 scripts/validate_data.py
py -3 -m unittest discover -s tests -v
py -3 -m http.server 8000
```

Abra `http://localhost:8000/`. No abra `index.html` directamente: el navegador
restringe las solicitudes `fetch()` desde `file://`.

## Principios para cambios de datos

1. Conserve el archivo oficial original sin modificaciones y registre su URL,
   jurisdicción, vigencia y tipo en `data/boundary-manifest.json`.
2. No infiera asociaciones por similitud de nombres. Cada feature debe estar
   resuelto explícitamente en `data/boundary-crosswalk.json` o marcado como no
   asociado con una razón.
3. Use identificadores de escuela estables. Los nombres son etiquetas, no
   llaves de unión.
4. No publique un rating como `verified` sin evidencia individual. Se admite
   una entrega autorizada o una tabla completa proporcionada por el usuario,
   siempre con método y procedencia diferenciados. No invente fechas, URLs ni
   valores ausentes.
5. No sustituya un límite de asistencia por un límite municipal o por una
   geometría aproximada. Registre el tipo correcto y deje visible la
   limitación.
6. No actualice únicamente el frontend: los JSON versionados constituyen la
   fuente de datos publicada.

Las fuentes externas conservan sus propios términos de uso y licencias. Antes
de añadir o redistribuir una capa, compruebe que la fuente permite ese uso y
documente la atribución correspondiente.

## Actualizar ratings

Los [Términos de uso de GreatSchools](https://www.greatschools.org/gk/terms/)
prohíben web scraping, web harvesting y web extraction. No añada scripts ni
navegadores automatizados para extraer ratings de sus páginas. Una actualización
puede proceder de una API/feed autorizado o de una tabla completa proporcionada
por el usuario, cuya procedencia debe quedar diferenciada explícitamente.

Antes de preparar un cambio:

1. Confirme por escrito que la licencia permite este uso, publicación,
   atribución y combinación con el mapa.
2. Configure la fuente permitida en `config/rating-sources.json` sin guardar
   API keys, tokens ni credenciales en el repositorio.
3. Compruebe las opciones disponibles con:

   ```powershell
   py -3 scripts/import_authorized_ratings.py --help
   ```

4. Ejecute primero el importador sin `--apply` y revise que resuelva 84 de 84
   escuelas, sin duplicados ni identidades ambiguas.
5. Aplique únicamente con `--apply` y `--license-confirmed`. La bandera confirma
   una revisión previa; no concede derechos adicionales.
6. Revise juntos `data/schools.json` y `data/rating-evidence.json`, y ejecute el
   validador y las pruebas.

Ejemplo de vista previa y aplicación, manteniendo el feed autorizado fuera del
repositorio cuando su licencia no permita redistribuirlo:

```powershell
py -3 scripts/import_authorized_ratings.py --input C:\secure\authorized-ratings.csv
py -3 scripts/import_authorized_ratings.py --input C:\secure\authorized-ratings.csv --apply --license-confirmed
```

Una importación de feed autorizada utiliza `authorized_bulk_feed` y debe dejar
por escuela una URL de fuente, fecha UTC de consulta y evidencia. Use
`rating_status`:

- `verified` para un valor 1–10 respaldado por evidencia;
- `not_available` únicamente cuando la entrega autorizada cubra expresamente la
  escuela sin proporcionar rating;
- `legacy_unverified` para los valores históricos sin evidencia.

Una tabla proporcionada por el usuario utiliza
`user_supplied_manual_verification`. Debe cubrir exactamente las 84 escuelas,
incluir `school_id`, URL individual, score, fecha y estado, y conservar en la
evidencia el nombre y SHA-256 del libro recibido. No se presenta como feed
autorizado ni como extracción realizada por el pipeline.
La copia preservada en `outputs/` debe coincidir byte por byte con ese hash.

La presentación cromática debe conservar los cinco rangos publicados:
9–10 verde intenso (`#1a9850`), 7–8 verde (`#91cf60`), 5–6 amarillo
(`#fee08b`), 3–4 naranja (`#fc8d59`) y 1–2 rojo intenso (`#d73027`). Un rating
ausente usa gris (`#727a80`) y nunca se sustituye por un valor estimado.

Un 403, CAPTCHA, timeout, error de red, error de parseo o resultado ambiguo no
es `not_available`: es un fallo del refresh. No complete la cobertura con el
rating anterior, un promedio, cero ni una estimación. El proceso debe terminar
sin modificar los archivos publicados.

No confirme ni publique una entrega parcial. No incluya el feed crudo si la
licencia no permite redistribuirlo y nunca incluya secretos en la evidencia.
`rating_as_of` contiene solo el año o mes declarado por la fuente; use `null`
si no lo declara. `rating_checked_at` registra por separado el instante real de
procesamiento en UTC.

## Comprobaciones obligatorias

Antes de proponer un cambio:

```powershell
py -3 scripts/validate_data.py
py -3 -m unittest discover -s tests -v
git diff --check
```

Sirva también el sitio por HTTP y revise al menos:

- carga sin errores en la consola;
- conteos y estado de cobertura;
- búsqueda y filtros;
- popup de una escuela con boundary y de una escuela sin boundary;
- navegación por teclado y presentación móvil.

## Alcance de cada pull request

Mantenga los cambios pequeños y auditables. Explique:

- qué problema resuelve;
- qué fuentes y vigencias cambian;
- cuántos ratings quedan `verified`, `not_available` y `legacy_unverified`;
- qué licencia autorizó el método, sin incluir secretos ni material privado;
- qué archivos derivados se regeneraron;
- qué validaciones ejecutó;
- qué excepciones o registros no asociados permanecen.

No incluya archivos temporales, entornos virtuales ni reemplazos masivos de
GeoJSON que no estén relacionados con el cambio.

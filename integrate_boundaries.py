"""
Script para integrar boundaries oficiales al mapa HTML
Lee los archivos .geojson descargados y actualiza index.html

Uso: python integrate_boundaries.py
"""

import json
import sys
from pathlib import Path

# Forzar UTF-8 en Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Archivos de boundaries esperados
BOUNDARY_FILES = [
    'fairfax_hs_boundaries.geojson',
    'montgomery_hs_boundaries.geojson',
    'arlington_hs_boundaries.geojson',
    'prince_georges_hs_boundaries.geojson',
    'alexandria_hs_boundaries.geojson',
    'dc_hs_boundaries.geojson'
]

def check_files():
    """Verifica que archivos GeoJSON estan disponibles"""
    found = []
    missing = []

    for filename in BOUNDARY_FILES:
        path = Path(filename)
        if path.exists():
            size_kb = path.stat().st_size / 1024
            found.append((filename, size_kb))
        else:
            missing.append(filename)

    return found, missing

def analyze_geojson(filename):
    """Analiza un archivo GeoJSON para entender su estructura"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if data.get('type') != 'FeatureCollection':
            return None, "No es un FeatureCollection valido"

        features = data.get('features', [])
        if not features:
            return None, "No contiene features"

        # Analizar primer feature
        first_feature = features[0]
        props = first_feature.get('properties', {})
        geom = first_feature.get('geometry', {})

        return {
            'num_features': len(features),
            'geometry_type': geom.get('type'),
            'properties': list(props.keys()),
            'sample_properties': props
        }, None

    except Exception as e:
        return None, str(e)

def match_school_to_boundary(school_name, boundary_props):
    """
    Intenta emparejar nombre de escuela con propiedades del boundary
    Retorna el nombre del campo que contiene el nombre de la escuela
    """
    school_name_lower = school_name.lower()

    # Campos comunes que podrían contener nombres de escuelas
    common_fields = ['NAME', 'SCHOOL_NAME', 'SchoolName', 'name', 'school',
                     'FACILITY', 'HS_NAME', 'HIGH_SCHOOL']

    for field in common_fields:
        if field in boundary_props:
            value = str(boundary_props[field]).lower()
            if value in school_name_lower or school_name_lower in value:
                return field

    return None

def create_html_with_boundaries(found_files):
    """
    Crea una nueva versión del HTML que carga boundaries desde archivos GeoJSON
    """
    print("\n" + "="*70)
    print("CREANDO HTML CON BOUNDARIES REALES")
    print("="*70)

    # Leer el HTML actual
    html_path = Path('index.html')
    if not html_path.exists():
        print("[ERROR] No se encuentra index.html")
        return False

    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Crear lista de archivos a cargar
    boundary_files_js = ',\n            '.join([f'"{f}"' for f, _ in found_files])

    # Codigo JavaScript para cargar boundaries
    load_boundaries_code = f'''
        // ============================================
        // CARGA DE BOUNDARIES REALES
        // ============================================

        const boundaryFiles = [
            {boundary_files_js}
        ];

        // Colores por rating
        const ratingColors = {{
            10: '#1a9850', 9: '#1a9850',
            8: '#91cf60', 7: '#91cf60',
            6: '#fee08b', 5: '#fee08b',
            4: '#fc8d59', 3: '#fc8d59',
            2: '#d73027', 1: '#d73027'
        }};

        // Funcion para encontrar rating de escuela por nombre
        function findSchoolRating(schoolName) {{
            const schoolNameLower = schoolName.toLowerCase();
            for (const school of highSchools) {{
                if (school.name.toLowerCase().includes(schoolNameLower) ||
                    schoolNameLower.includes(school.name.toLowerCase())) {{
                    return school.rating;
                }}
            }}
            return null;
        }}

        // Cargar cada archivo de boundaries
        async function loadBoundaries() {{
            for (const file of boundaryFiles) {{
                try {{
                    const response = await fetch(file);
                    if (!response.ok) continue;

                    const data = await response.json();

                    L.geoJSON(data, {{
                        style: function(feature) {{
                            // Intentar obtener nombre de escuela de las propiedades
                            const props = feature.properties;
                            const schoolName = props.NAME || props.SCHOOL_NAME ||
                                              props.SchoolName || props.name ||
                                              props.FACILITY || props.school || '';

                            const rating = findSchoolRating(schoolName) || 5;
                            const color = ratingColors[rating] || '#999';

                            return {{
                                fillColor: color,
                                weight: 2,
                                opacity: 0.8,
                                color: color,
                                fillOpacity: 0.5
                            }};
                        }},
                        onEachFeature: function(feature, layer) {{
                            const props = feature.properties;
                            const schoolName = props.NAME || props.SCHOOL_NAME ||
                                              props.SchoolName || props.name ||
                                              props.FACILITY || props.school || 'Escuela desconocida';

                            const rating = findSchoolRating(schoolName);

                            if (rating) {{
                                const color = ratingColors[rating];
                                const popupContent = `
                                    <div class="popup-title">${{schoolName}}</div>
                                    <div class="popup-rating" style="background-color: ${{color}}">
                                        ${{rating}}/10
                                    </div>
                                    <div style="font-size: 11px; color: #666;">
                                        ${{getRatingDescription(rating)}}
                                    </div>
                                `;
                                layer.bindPopup(popupContent);
                            }}
                        }}
                    }}).addTo(allSchoolsLayer);

                    console.log(`[OK] Cargado: ${{file}}`);
                }} catch (error) {{
                    console.warn(`[AVISO] No se pudo cargar ${{file}}:`, error.message);
                }}
            }}
        }}

        // Cargar boundaries al iniciar
        loadBoundaries();

        console.log('Intentando cargar', boundaryFiles.length, 'archivos de boundaries...');
'''

    # Insertar antes del cierre del script
    insert_marker = 'console.log(\'Mapa cargado con\', highSchools.length, \'escuelas\');'
    if insert_marker in html_content:
        html_content = html_content.replace(
            insert_marker,
            load_boundaries_code + '\n        ' + insert_marker
        )

        # Guardar nuevo HTML
        output_path = Path('index_with_boundaries.html')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"[OK] Creado: {output_path}")
        print(f"     Este archivo carga boundaries reales desde archivos GeoJSON")
        return True
    else:
        print("[ERROR] No se pudo encontrar el punto de insercion en el HTML")
        return False

def main():
    print("="*70)
    print("INTEGRACION DE BOUNDARIES OFICIALES")
    print("="*70)

    # Verificar archivos
    found, missing = check_files()

    print(f"\nArchivos encontrados: {len(found)}")
    for filename, size_kb in found:
        print(f"  [OK] {filename} ({size_kb:.1f} KB)")

    if missing:
        print(f"\nArchivos faltantes: {len(missing)}")
        for filename in missing:
            print(f"  [FALTA] {filename}")

    if not found:
        print("\n[ERROR] No se encontro ningun archivo GeoJSON")
        print("        Lee MANUAL_DOWNLOAD_INSTRUCTIONS.md para descargarlos")
        return

    # Analizar archivos encontrados
    print("\n" + "="*70)
    print("ANALISIS DE ARCHIVOS")
    print("="*70)

    for filename, _ in found:
        print(f"\n{filename}:")
        info, error = analyze_geojson(filename)

        if error:
            print(f"  [ERROR] {error}")
        else:
            print(f"  Features: {info['num_features']}")
            print(f"  Tipo de geometria: {info['geometry_type']}")
            print(f"  Propiedades: {', '.join(info['properties'][:5])}")

            # Mostrar muestra de propiedades
            if info['sample_properties']:
                print(f"  Ejemplo de valores:")
                for key, value in list(info['sample_properties'].items())[:3]:
                    print(f"    - {key}: {value}")

    # Crear HTML con boundaries
    if create_html_with_boundaries(found):
        print("\n" + "="*70)
        print("COMPLETADO")
        print("="*70)
        print("Abre 'index_with_boundaries.html' en tu navegador")
        print("Los boundaries oficiales se mostraran superpuestos a los aproximados")
    else:
        print("\n[ERROR] No se pudo crear el HTML con boundaries")

if __name__ == '__main__':
    main()

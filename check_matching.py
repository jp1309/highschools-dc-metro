"""
Script para verificar que los nombres de escuelas en el HTML
coincidan con los nombres en los archivos GeoJSON
"""

import json
import re
import sys

# Fix encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Leer archivos GeoJSON
geojson_files = {
    'Arlington': ('arlington_hs_boundaries.geojson', 'HS_Name'),
    'Fairfax': ('fairfax_hs_boundaries.geojson', 'SCHOOL_NAME'),
    'Montgomery': ('montgomery_hs_boundaries.geojson', 'S_NAME'),
    'Alexandria': ('alexandria_hs_boundaries.geojson', 'NAME')
}

# Nombres de escuelas del HTML (solo las 3 de Arlington para prueba)
html_schools = {
    'Arlington': [
        "Yorktown High School",
        "Washington-Liberty High School",
        "Wakefield High School"
    ]
}

def normalize_name(name):
    """Normaliza nombre de escuela para comparación"""
    normalized = name.lower()
    normalized = normalized.replace(' high school', '')
    normalized = normalized.replace(' hs', '')
    normalized = normalized.replace(' secondary', '')
    return normalized.strip()

print("=" * 60)
print("VERIFICACIÓN DE MATCHING DE NOMBRES")
print("=" * 60)

for jurisdiction, (filename, prop_name) in geojson_files.items():
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"\n{jurisdiction} ({filename}):")
        print(f"  Total features: {len(data['features'])}")

        # Listar primeras 3 escuelas
        print(f"  Nombres en GeoJSON (primeros 3):")
        for i, feature in enumerate(data['features'][:3]):
            school_name = feature['properties'].get(prop_name, 'N/A')
            print(f"    - {school_name}")

        # Si tenemos escuelas del HTML para esta jurisdicción, verificar matching
        if jurisdiction in html_schools:
            print(f"\n  Verificando matching con HTML:")
            for html_name in html_schools[jurisdiction]:
                html_normalized = normalize_name(html_name)

                # Buscar coincidencia
                found = False
                for feature in data['features']:
                    geojson_name = feature['properties'].get(prop_name, '')
                    geojson_normalized = normalize_name(geojson_name)

                    if (html_normalized == geojson_normalized or
                        html_normalized in geojson_normalized or
                        geojson_normalized in html_normalized):
                        print(f"    ✓ '{html_name}' → '{geojson_name}' (MATCH)")
                        found = True
                        break

                if not found:
                    print(f"    ✗ '{html_name}' → NO ENCONTRADO")

    except FileNotFoundError:
        print(f"\n{jurisdiction}: Archivo no encontrado ({filename})")
    except Exception as e:
        print(f"\n{jurisdiction}: Error - {e}")

print("\n" + "=" * 60)

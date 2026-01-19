"""
Script para descargar boundaries oficiales de high schools
del area metropolitana de Washington DC

Requiere: requests
Instalar con: pip install requests
"""

import json
import requests
import time
import sys
from pathlib import Path

# Forzar UTF-8 en Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# URLs de APIs de ArcGIS REST Services
BOUNDARY_SOURCES = {
    'fairfax': {
        'name': 'Fairfax County High School Boundaries',
        'url': 'https://services1.arcgis.com/ioennV6PpG5Xodq0/arcgis/rest/services/High_School_Attendance_Areas/FeatureServer/0/query',
        'params': {
            'where': '1=1',
            'outFields': '*',
            'f': 'geojson',
            'returnGeometry': 'true'
        },
        'output': 'fairfax_hs_boundaries.geojson'
    },
    'montgomery': {
        'name': 'Montgomery County High School Boundaries',
        'url': 'https://gisdata.montgomerycountymd.gov/arcgis/rest/services/Planning/High_School_Boundaries/MapServer/0/query',
        'params': {
            'where': '1=1',
            'outFields': '*',
            'f': 'geojson',
            'returnGeometry': 'true'
        },
        'output': 'montgomery_hs_boundaries.geojson'
    },
    'arlington': {
        'name': 'Arlington County School Boundaries',
        'url': 'https://services.arcgis.com/d3voDfTFbHOCRwVR/arcgis/rest/services/SchoolBoundaries/FeatureServer/2/query',
        'params': {
            'where': '1=1',
            'outFields': '*',
            'f': 'geojson',
            'returnGeometry': 'true'
        },
        'output': 'arlington_hs_boundaries.geojson'
    },
    'prince_georges': {
        'name': 'Prince George\'s County High School Boundaries',
        'url': 'https://onlinegis.princegeorgescountymd.gov/arcgis/rest/services/SCHOOLS/SchoolBoundaries/MapServer/2/query',
        'params': {
            'where': '1=1',
            'outFields': '*',
            'f': 'geojson',
            'returnGeometry': 'true'
        },
        'output': 'prince_georges_hs_boundaries.geojson'
    },
    'dc': {
        'name': 'Washington DC School Boundaries',
        'url': 'https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Education_WebMercator/MapServer/9/query',
        'params': {
            'where': '1=1',
            'outFields': '*',
            'f': 'geojson',
            'returnGeometry': 'true'
        },
        'output': 'dc_school_boundaries.geojson'
    },
    'alexandria': {
        'name': 'Alexandria City School Boundaries',
        'url': 'https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/School_Attendance_Zones/FeatureServer/2/query',
        'params': {
            'where': '1=1',
            'outFields': '*',
            'f': 'geojson',
            'returnGeometry': 'true'
        },
        'output': 'alexandria_hs_boundaries.geojson'
    }
}

def download_boundary(key, config):
    """Descarga un archivo de boundaries desde una API de ArcGIS"""
    print(f"\n{'='*60}")
    print(f"Descargando: {config['name']}")
    print(f"URL: {config['url']}")

    try:
        response = requests.get(
            config['url'],
            params=config['params'],
            timeout=30
        )

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            # Intentar parsear como JSON
            try:
                data = response.json()

                # Verificar si es GeoJSON válido
                if 'type' in data and 'features' in data:
                    num_features = len(data.get('features', []))
                    print(f"[OK] GeoJSON válido con {num_features} features")

                    # Guardar archivo
                    output_path = Path(config['output'])
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)

                    print(f"[OK] Guardado en: {output_path}")
                    return True
                else:
                    print(f"[ERROR] Respuesta no es GeoJSON válido")
                    print(f"  Estructura: {list(data.keys())[:5]}")

                    # Guardar respuesta para inspección
                    debug_path = Path(f"debug_{key}.json")
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                    print(f"  Respuesta guardada en: {debug_path}")
                    return False

            except json.JSONDecodeError as e:
                print(f"[ERROR] Error al parsear JSON: {e}")
                print(f"  Primeros 500 caracteres: {response.text[:500]}")
                return False
        else:
            print(f"[ERROR] Error HTTP: {response.status_code}")
            print(f"  Respuesta: {response.text[:500]}")
            return False

    except requests.exceptions.Timeout:
        print(f"[ERROR] Timeout - El servidor tardó demasiado en responder")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"[ERROR] Error de conexión: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Error inesperado: {e}")
        return False

def main():
    print("="*60)
    print("DESCARGA DE BOUNDARIES DE HIGH SCHOOLS")
    print("Área Metropolitana de Washington DC")
    print("="*60)

    # Verificar que requests esté instalado
    try:
        import requests
    except ImportError:
        print("\n[ERROR] ERROR: El módulo 'requests' no está instalado")
        print("  Instala con: pip install requests")
        return

    results = {}

    for key, config in BOUNDARY_SOURCES.items():
        success = download_boundary(key, config)
        results[key] = success

        # Pausa entre requests para no sobrecargar los servidores
        if key != list(BOUNDARY_SOURCES.keys())[-1]:
            time.sleep(2)

    # Resumen final
    print("\n" + "="*60)
    print("RESUMEN DE DESCARGAS")
    print("="*60)

    successful = sum(1 for v in results.values() if v)
    total = len(results)

    for key, success in results.items():
        status = "[OK]" if success else "[ERROR]"
        name = BOUNDARY_SOURCES[key]['name']
        print(f"{status} {name}")

    print(f"\nTotal: {successful}/{total} descargas exitosas")

    if successful > 0:
        print("\n" + "="*60)
        print("PRÓXIMOS PASOS:")
        print("="*60)
        print("1. Revisa los archivos .geojson descargados")
        print("2. Ejecuta: python integrate_boundaries.py")
        print("   (Este script integrará los boundaries al mapa HTML)")
    else:
        print("\n[AVISO] No se pudo descargar ningún archivo.")
        print("Revisa los archivos debug_*.json para más información.")

if __name__ == '__main__':
    main()

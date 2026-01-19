"""
Script mejorado para descargar boundaries de high schools
Usa URLs alternativas y metodos de descarga directa

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

# URLs alternativas usando metodos diferentes
BOUNDARY_SOURCES = {
    'fairfax': {
        'name': 'Fairfax County High School Boundaries',
        'method': 'arcgis_api',
        'url': 'https://services1.arcgis.com/ioennV6PpG5Xodq0/ArcGIS/rest/services/High_School_Attendance_Areas/FeatureServer/0/query',
        'params': {
            'where': '1=1',
            'outFields': '*',
            'outSR': '4326',
            'f': 'geojson'
        },
        'output': 'fairfax_hs_boundaries.geojson'
    },
    'montgomery': {
        'name': 'Montgomery County High School Boundaries',
        'method': 'direct_download',
        'url': 'https://data-mcplanning.hub.arcgis.com/api/download/v1/items/543af29c9b564694b7b62bd22cd0933b/geojson',
        'output': 'montgomery_hs_boundaries.geojson'
    },
    'arlington': {
        'name': 'Arlington County High School Boundaries',
        'method': 'arcgis_api',
        'url': 'https://services.arcgis.com/d3voDfTFbHOCRwVR/ArcGIS/rest/services/SchoolBoundaries/FeatureServer/2/query',
        'params': {
            'where': "LEVEL='HS' OR LEVEL='High'",
            'outFields': '*',
            'outSR': '4326',
            'f': 'geojson'
        },
        'output': 'arlington_hs_boundaries.geojson'
    },
    'dc_open_data': {
        'name': 'Washington DC High School Zones (OpenData)',
        'method': 'direct_download',
        'url': 'https://opendata.arcgis.com/datasets/98e2eaef4cc446e58da63cf14f1c8685_11.geojson',
        'output': 'dc_hs_boundaries.geojson'
    },
    'prince_georges': {
        'name': 'Prince Georges County School Boundaries',
        'method': 'arcgis_api',
        'url': 'https://services.arcgis.com/kLz44Olt1k6zoOaU/ArcGIS/rest/services/SchoolBoundaries/FeatureServer/2/query',
        'params': {
            'where': '1=1',
            'outFields': '*',
            'outSR': '4326',
            'f': 'geojson'
        },
        'output': 'prince_georges_hs_boundaries.geojson'
    }
}

def download_arcgis_api(config):
    """Descarga desde una API de ArcGIS REST"""
    try:
        response = requests.get(
            config['url'],
            params=config.get('params', {}),
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()

            if 'type' in data and 'features' in data:
                return data, None
            elif 'error' in data:
                return None, f"Error del servidor: {data['error']}"
            else:
                return None, f"Respuesta no es GeoJSON valido: {list(data.keys())}"
        else:
            return None, f"HTTP {response.status_code}: {response.text[:200]}"

    except Exception as e:
        return None, str(e)

def download_direct(config):
    """Descarga directa de archivo GeoJSON"""
    try:
        response = requests.get(
            config['url'],
            timeout=60,
            allow_redirects=True
        )

        if response.status_code == 200:
            # Verificar si es JSON
            try:
                data = response.json()
                if 'type' in data and 'features' in data:
                    return data, None
                else:
                    return None, f"Archivo descargado pero no es GeoJSON: {list(data.keys())}"
            except:
                return None, "No se puede parsear como JSON"
        else:
            return None, f"HTTP {response.status_code}"

    except Exception as e:
        return None, str(e)

def download_boundary(key, config):
    """Descarga un archivo de boundaries"""
    print(f"\n{'='*70}")
    print(f"Descargando: {config['name']}")
    print(f"Metodo: {config['method']}")
    print(f"URL: {config['url']}")

    # Seleccionar metodo
    if config['method'] == 'arcgis_api':
        data, error = download_arcgis_api(config)
    elif config['method'] == 'direct_download':
        data, error = download_direct(config)
    else:
        data, error = None, "Metodo desconocido"

    if data:
        num_features = len(data.get('features', []))
        print(f"[OK] GeoJSON valido con {num_features} features")

        # Mostrar algunas propiedades
        if num_features > 0:
            props = data['features'][0].get('properties', {})
            print(f"     Campos disponibles: {', '.join(list(props.keys())[:5])}")

        # Guardar archivo
        output_path = Path(config['output'])
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        file_size = output_path.stat().st_size / 1024
        print(f"[OK] Guardado: {output_path} ({file_size:.1f} KB)")
        return True
    else:
        print(f"[ERROR] {error}")
        return False

def main():
    print("="*70)
    print("DESCARGA DE BOUNDARIES DE HIGH SCHOOLS v2")
    print("Area Metropolitana de Washington DC")
    print("="*70)

    # Verificar requests
    try:
        import requests
    except ImportError:
        print("\n[ERROR] El modulo 'requests' no esta instalado")
        print("        Instala con: pip install requests")
        return

    results = {}

    for key, config in BOUNDARY_SOURCES.items():
        success = download_boundary(key, config)
        results[key] = success
        time.sleep(2)

    # Resumen
    print("\n" + "="*70)
    print("RESUMEN DE DESCARGAS")
    print("="*70)

    successful = sum(1 for v in results.values() if v)
    total = len(results)

    for key, success in results.items():
        status = "[OK]" if success else "[ERROR]"
        name = BOUNDARY_SOURCES[key]['name']
        print(f"{status} {name}")

    print(f"\nExitosas: {successful}/{total}")

    if successful > 0:
        print("\n" + "="*70)
        print("ARCHIVOS DESCARGADOS:")
        print("="*70)
        for key, success in results.items():
            if success:
                output = BOUNDARY_SOURCES[key]['output']
                print(f"  - {output}")

        print("\n[SIGUIENTE] Ejecuta: python integrate_boundaries.py")
    else:
        print("\n[AVISO] No se pudo descargar ningun archivo.")
        print("        Algunas jurisdicciones no tienen boundaries publicos disponibles.")

if __name__ == '__main__':
    main()

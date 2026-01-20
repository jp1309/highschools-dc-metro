import json

with open('princegeorge_hs_boundaries.geojson', 'r', encoding='utf-8') as f:
    data = json.load(f)

def get_centroid(coords):
    """Calculate centroid of a polygon"""
    if not coords or not coords[0]:
        return None, None

    # Get first polygon (exterior ring)
    polygon = coords[0]

    # Calculate centroid
    x_sum = sum(point[0] for point in polygon)
    y_sum = sum(point[1] for point in polygon)
    n = len(polygon)

    return round(x_sum / n, 6), round(y_sum / n, 6)

schools = {}
for feature in data['features']:
    name = feature['properties'].get('NAME', feature['properties'].get('school_name', 'Unknown'))
    geom = feature['geometry']

    if geom['type'] == 'Polygon':
        lng, lat = get_centroid(geom['coordinates'])
    elif geom['type'] == 'MultiPolygon':
        # Use the first polygon of the multipolygon
        lng, lat = get_centroid(geom['coordinates'][0])
    else:
        lng, lat = None, None

    schools[name] = {'lat': lat, 'lng': lng}

# Print in a format easy to copy
for name, coords in sorted(schools.items()):
    print(f"{name}: {coords['lat']}, {coords['lng']}")

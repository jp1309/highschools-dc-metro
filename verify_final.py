import re

# Leer el archivo HTML
with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Buscar todas las escuelas por jurisdicción
jurisdictions = {
    "Fairfax County, VA": [],
    "Montgomery County, MD": [],
    "Arlington, VA": [],
    "Prince George's County, MD": [],
    "Alexandria City, VA": [],
    "Falls Church City, VA": [],
    "Washington, DC": []
}

# Pattern para encontrar escuelas
pattern = r'name:\s*"([^"]+)",\s*address:[^}]+jurisdiction:\s*"([^"]+)"'
matches = re.findall(pattern, content)

for name, jurisdiction in matches:
    if jurisdiction in jurisdictions:
        jurisdictions[jurisdiction].append(name)

# Imprimir resultados
print("=" * 60)
print("VERIFICACIÓN FINAL - ESCUELAS POR JURISDICCIÓN")
print("=" * 60)
print()

total = 0
for jurisdiction, schools in jurisdictions.items():
    count = len(schools)
    total += count
    print(f"{jurisdiction}")
    print(f"  Total: {count} escuelas")
    if count > 0:
        for i, school in enumerate(sorted(schools), 1):
            print(f"  {i}. {school}")
    print()

print("=" * 60)
print(f"TOTAL DE ESCUELAS: {total}")
print("=" * 60)

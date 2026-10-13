# Datos geoespaciales de apoyo

Archivos que se versionan junto al backend. Todos en EPSG:4326 (lon, lat).

| Archivo | Qué es | Fuente |
|---|---|---|
| `distritos_gamsc.geojson` | 16 distritos municipales (+ "Área Urbana" y "limite jurisdiccional", que no son distritos) | API pública de la Guía Urbana del GAMSC (`guiaurbana.gmsantacruz.gob.bo`), obtenida con `Sistema/distrito/scriptdistrito.py` el 2026-10-13 |
| `predios_osm_santacruz.geojson` | 472 contornos con nombre: salud, educativo, comercial, mercados e industrial | OpenStreetMap, el 2026-10-13 |
| `hidrantes_osm_santacruz.geojson` | 7 hidrantes | OpenStreetMap, el 2026-10-13 |

## Licencia y atribución (OpenStreetMap)

Los predios y hidrantes son © colaboradores de OpenStreetMap, bajo licencia ODbL
(<https://www.openstreetmap.org/copyright>). **Hay que citarlo** en la tesis y en cualquier
pantalla o reporte que muestre estos datos: "© OpenStreetMap contributors".

## Cómo se generaron los archivos de OpenStreetMap

Consulta a Overpass sobre el rectángulo de la ciudad `(-17.90, -63.26, -17.66, -63.04)`:

- Contornos (`way`) con `amenity` = hospital, clinic, school, university o marketplace;
  `shop` = mall, supermarket o department_store; `building` = industrial o warehouse con nombre.
- Nodos con `emergency=fire_hydrant`.

Luego se descartaron los que no tienen nombre y los de área menor a 80 m² o mayor a 500 000 m², y
cada elemento se asignó a un tipo del catálogo: hospital/clinic → Salud; school/university →
Educativo; marketplace → Mercado Distrital; mall/supermarket/department_store → Comercial;
industrial/warehouse → Industrial.

## Cargar los distritos (datos reales)

```
docker compose run --rm web python manage.py importar_distritos datos/distritos_gamsc.geojson --excluir "Área Urbana" "limite jurisdiccional" --reparar
```

## Cargar datos de demostración (inspecciones SIMULADAS)

Para probar mapa de calor, zonas sugeridas y clustering sin esperar inspecciones reales:

```
docker compose run --rm web python manage.py cargar_datos_demo              # 15 predios por tipo
docker compose run --rm web python manage.py cargar_datos_demo --por-tipo 30
docker compose run --rm web python manage.py cargar_datos_demo --borrar     # quita TODO lo demo
```

Los **predios y hidrantes son reales** (OpenStreetMap); las **actas son ficticias**: las genera una
simulación con semilla, y la carga de fuego y el scoring salen del cálculo oficial del sistema.
Todo queda marcado (`atributos_extra.demo`, campaña `[DEMO]…`, hidrantes `DEMO-OSM-*`, inspector
`demo.inspector@uubr.invalid`). **No presentar estos resultados como inspecciones reales y
borrarlos (`--borrar`) antes de usar el sistema en producción.**

# Mapa de las UGEL del Perú

Polígonos GeoJSON de las **226 Unidades de Gestión Educativa Local (UGEL)** del Perú, con el
número de instituciones educativas de cada una según ESCALE. Incluye una librería sin
dependencias para dibujarlos como mapa coroplético.

No existe un shapefile oficial de jurisdicciones UGEL. Estos polígonos se construyen
agrupando los distritos que administra cada UGEL, deducidos de la ubicación real de sus
colegios. Todo el proceso es reproducible con los scripts de `tools/`.

> ### ⚠️ Antes de usarlo
> Estos polígonos son **aproximados** y **no son cartografía oficial**. No determinan a qué
> UGEL pertenece una institución educativa, ni sirven para trámites o actos administrativos.
> Sobre 16 540 colegios verificados, el 92,8 % cae dentro del polígono de su propia UGEL;
> el 7,2 % no, porque hay 96 distritos que dos UGEL se reparten y un distrito no se puede
> partir en dos.
>
> **[Lee el aviso completo →](AVISO.md)**

**[Ver el mapa en vivo](https://swamperu.github.io/peru-ugel-geojson/)**

---

## Los datos

| Archivo | Contenido | Identificador | Peso |
|---|---|---|---|
| `data/peru-ugel.json` | 226 UGEL | `codigo` (6 díg.) | 677 KB |
| `data/peru-regiones.json` | 25 regiones (24 dptos + Callao) | `codigo` (2 díg.) | 266 KB |
| `data/peru-distritos.json` | 1 890 distritos | `ubigeo` (6 díg.) | 1,7 MB |
| `data/escale-colegios.json` | Colegios de EBR por UGEL y región, con nivel y área | | 39 KB |
| `data/ugel-catalogo.csv` | Las 226 UGEL, su código oficial y **cómo se construyó cada polígono** | | 12 KB |
| `data/ugel-distrito.csv` | Mapeo ubigeo → UGEL (1 892 distritos) | | 57 KB |

Las tres capas geográficas se derivan del **mismo** archivo distrital del INEI, así que
comparten vértices exactos: al superponerlas no se dibujan bordes dobles ni quedan franjas
entre polígonos.

Los códigos llevan **ceros a la izquierda y son texto**. Amazonas es `"01"`, no `1`. Si tu
código los convierte a número, la mitad del mapa va a quedar sin datos.

### Propiedades de cada UGEL

```json
{
  "codigo": "150102",
  "nombre": "UGEL 01 SAN JUAN DE MIRAFLORES",
  "region": "15",
  "distritos": 11,
  "pendiente": false
}
```

### Uso directo, sin descargar nada

```js
const ugel = await fetch(
  'https://cdn.jsdelivr.net/gh/swamperu/peru-ugel-geojson@main/data/peru-ugel.json'
).then(r => r.json());
```

Funciona con Leaflet, D3, ECharts, Mapbox, geopandas o lo que uses.

---

## Probar con tus propios datos, sin programar

Si solo quieres ver tus cifras pintadas en el mapa:

1. Abre **[la página de carga](https://swamperu.github.io/peru-ugel-geojson/probar.html)**.
2. Arrastra tu Excel o CSV. El archivo se procesa en tu navegador: no se sube a ningún lado.
3. Listo. La página detecta sola la columna que identifica la UGEL y la del valor, y te dice
   cuántas filas cruzaron.

Tu archivo solo necesita dos columnas: una que identifique la UGEL y otra con el número a
pintar. **El identificador puede ser el código o el nombre.** Reconoce los nombres aunque
difieran en tildes, mayúsculas o el prefijo "UGEL", así que `UGEL 01 San Juan de Miraflores`,
`SAN JUAN DE MIRAFLORES` y `150102` llegan todos al mismo polígono.

Si el código perdió el cero inicial al abrirlo en Excel (`10001` en vez de `010001`), también
lo resuelve.

¿No tienes el archivo armado? Descarga
**[`plantilla-ugel.xlsx`](plantilla-ugel.xlsx)**: trae los 226 códigos y nombres, más el
número de colegios de cada UGEL por si necesitas calcular tasas. Pegas tus cifras en la
columna amarilla y la arrastras a la página.

---

## La librería

`src/peru-map.js` dibuja estos polígonos como mapa coroplético. Sin dependencias: ni D3, ni
Leaflet, ni tiles externos. Unos 600 KB de datos y 22 KB de código.

```html
<link rel="stylesheet" href="src/peru-map.css">
<div id="mapa" style="height:520px"></div>

<script type="module">
import { PeruMap } from './src/peru-map.js';

const mapa = new PeruMap('#mapa', {
  paleta: 'teal',
  tituloLeyenda: 'Colegios',
  tooltip: (f, valor) => `<strong>${f.nombre}</strong><span>${valor}</span>`,
  onClick: (id) => console.log(id),
});

await mapa.cargarGeografia('data/peru-ugel.json', {
  campoId: 'codigo', campoNombre: 'nombre'
});
mapa.setDatos(filas, { campoId: 'id', campoValor: 'total' });
</script>
```

| Método | Qué hace |
|---|---|
| `cargarGeografia(geojson\|url, {campoId, campoNombre})` | Carga o reemplaza la capa. |
| `setDatos(filas, {campoId, campoValor})` | Une por código y repinta. |
| `setContorno(geojson\|null)` | Capa de bordes encima, sin relleno ni eventos. |
| `setOpciones({...})` | Cambia paleta, escala o formato en caliente. |
| `seleccionar(id)` / `limpiarSeleccion()` | Resalta y atenúa el resto. |
| `zoomA(id)` / `resetZoom()` | Encuadre animado sobre un polígono. |
| `exportarSVG()` | Devuelve el SVG como string. |

Las etiquetas se dibujan en coordenadas de pantalla: **no crecen al hacer zoom**, y las que se
encimarían o caen sobre un polígono muy chico se descartan, dando prioridad a los grandes.

Paletas: `teal`, `indigo`, `ambar`, `brecha` (divergente), o un array de colores. Escalas:
`cuantil` (por defecto), `intervalo` o `cortes` propios.

---

## Regenerar desde las fuentes

```bash
# 1. Descarga los límites distritales (.gpkg) del geoportal del INEI: ide.inei.gob.pe
python tools/gpkg_a_geojson.py DISTRITO.gpkg -o distritos_inei.geojson

# 2. Cruza el padrón de ESCALE con la geometría
python tools/preparar_escale.py DATA_ESCALE.csv --distritos distritos_inei.geojson

# 3. Construye las capas
python tools/construir_geometria.py --distritos distritos_inei.geojson \
    --mapeo-csv data/ugel-distrito.csv --simplificar 0.004

# 4. Verifica que todo quedó consistente
python tools/verificar.py
```

Solo stdlib: no necesita GDAL, geopandas ni shapely. El conversor de GeoPackage lee el archivo
con `sqlite3` y `struct`, porque un `.gpkg` es una base SQLite con la geometría en WKB.

**`--simplificar` no es opcional.** La capa del INEI viene a resolución plena: sin simplificar,
`peru-distritos.json` pasa de 30 MB. La tolerancia va en grados (`0.004` ≈ 400 m) y quita el
96 % de los vértices sin diferencia visible a escala nacional. La simplificación **respeta la
topología**: las fronteras compartidas se parten en arcos y cada arco se simplifica una sola
vez, así los dos lados quedan con los mismos vértices.

### Corregir una jurisdicción

Agrega un `data/ugel-<zona>.csv` con columnas `ubigeo,cod_ugel,nom_ugel` y vuelve a correr los
pasos 2 y 3. El mapeo es acumulativo y los archivos se leen en orden, con
`ugel-correcciones.csv` al final, así que una corrección puntual gana sobre la asignación
provincial.

Si tienes el padrón con latitud y longitud, no hace falta la resolución de creación de la
UGEL:

```bash
python tools/ugel_desde_coordenadas.py colegios.csv \
    --distritos distritos_inei.geojson --nombre <zona>
```

Ubica cada colegio en su distrito por punto-en-polígono y gana la UGEL con más colegios. Avisa
de los distritos repartidos y descarta duplicados.

> Un distrito solo debe reasignarse si la UGEL que lo tenía **también** aparece en el archivo.
> Si no, unos pocos colegios sueltos ganan por ausencia del contrincante y el resultado es
> falso. El script no aplica esa regla por sí solo: revísalo antes de incorporar su salida.

---

## Cómo se resolvió cada UGEL

`data/ugel-catalogo.csv` lo declara una por una:

- **59 `distrital`** — lista de distritos verificada contra organigramas oficiales o
  ubicando los colegios por coordenadas (Lima Metropolitana, Condorcanqui, Bagua, Arequipa,
  Trujillo, el VRAEM, Loreto y las demás UGEL sub-provinciales).
- **167 `provincia`** — la UGEL cubre una provincia completa y el polígono es exacto.

Casos que muestran por qué no se puede asumir "UGEL = provincia":

- **UGEL 01 de Lima administra Chilca**, que pertenece a la provincia de Cañete.
- **Condorcanqui tiene tres distritos y tres UGEL**: una por distrito.
- **UGEL Caylloma administra Chachas y Choco**, en la provincia de Castilla.
- **UGEL Río Ene - Mantaro** existe solo en Vizcatán del Ene; en Pangoa, Mazamari y Río Tambo
  opera sin ser mayoría en ninguno.

### Polígonos con hueco o en dos partes

No son errores:

- **Arequipa Sur, Parinacochas, Canas y Puno** tienen un hueco interior. Son lagunas (Salinas,
  Parinacochas, Langui-Layo, Titicaca) que el INEI excluye del polígono distrital.
- **La Joya, Datem del Marañón y Yunguyo** salen en dos bloques: su jurisdicción no es
  contigua.

---

## Fuentes y licencia

- **Límites distritales**: límites censales del INEI (`ide.inei.gob.pe`). Son referenciales,
  no demarcatorios.
- **Instituciones educativas y catálogo de UGEL**: ESCALE – MINEDU.

El **código** (`src/`, `tools/`, `index.html`) se publica bajo licencia MIT: ver
[`LICENSE`](LICENSE).

Los **datos derivados** (`data/`) se ofrecen para uso libre citando este repositorio y la
fuente original de cada capa. Los datos de origen mantienen las condiciones de sus
respectivas entidades.

Cita sugerida:

> Mapa de las UGEL del Perú (2026). Polígonos GeoJSON de jurisdicción UGEL derivados de
> límites censales del INEI y del padrón de ESCALE – MINEDU.
> github.com/swamperu/peru-ugel-geojson

Proyecto independiente. No representa al MINEDU ni a ninguna entidad del Estado.
Lee el [aviso de uso y limitaciones](AVISO.md) antes de usar estos datos.

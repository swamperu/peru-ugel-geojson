#!/usr/bin/env python3
"""
construir_geometria.py — genera las capas GeoJSON que consume PeruMap.

Entrada única (descargar una vez de github.com/juaneladio/peru-geojson):
    peru_distrital_simple.geojson

Las tres capas se derivan del MISMO archivo distrital: así comparten vértices exactos y
las fronteras no se dibujan dobles al superponerlas.

Salidas en data/:
    peru-regiones.json      25 regiones (24 dptos + Callao)
    peru-distritos.json     1834 distritos, ubigeo de 6 dígitos
    peru-ugel.json          UGEL disueltas desde distritos

El mapeo distrito -> UGEL sale de tu base (ver mapeo_desde_sql / mapeo_desde_csv).
Sin mapeo, el script cae a provincia como proxy de UGEL.

Sin dependencias externas: solo stdlib.
"""

import argparse, collections, csv, json, math, os, sys, unicodedata

PRECISION = 4  # ~11 m. Suficiente para un mapa nacional y reduce el archivo ~4x.


# ───────────────────────── utilidades de geometría ─────────────────────────

def anillos(geom):
    """Devuelve la lista de polígonos (cada uno lista de anillos) de cualquier geometría."""
    if not geom:
        return []
    if geom['type'] == 'Polygon':
        return [geom['coordinates']]
    if geom['type'] == 'MultiPolygon':
        return geom['coordinates']
    return []


# ───────────────────────── simplificación topológica ─────────────────────────

def _dp(pts, tol):
    """Douglas-Peucker iterativo sobre una polilínea."""
    if len(pts) < 3:
        return pts
    guardar = [False] * len(pts)
    guardar[0] = guardar[-1] = True
    pila = [(0, len(pts) - 1)]
    while pila:
        i, j = pila.pop()
        if j <= i + 1:
            continue
        x1, y1 = pts[i]; x2, y2 = pts[j]
        dx, dy = x2 - x1, y2 - y1
        norma = dx * dx + dy * dy
        peor, idx = -1.0, i
        for k in range(i + 1, j):
            x, y = pts[k]
            if norma == 0:
                d = (x - x1) ** 2 + (y - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / norma))
                d = (x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2
            if d > peor:
                peor, idx = d, k
        if peor > tol * tol:
            guardar[idx] = True
            pila.append((i, idx)); pila.append((idx, j))
    return [p for p, g in zip(pts, guardar) if g]


def simplificar_topologico(features, tol):
    """
    Simplifica preservando la topología: la frontera compartida entre dos distritos
    se parte en arcos y CADA ARCO SE SIMPLIFICA UNA SOLA VEZ, de modo que ambos lados
    reciben exactamente los mismos vértices. Simplificar cada anillo por separado
    abriría huecos y franjas entre polígonos vecinos, y rompería la disolución.
    """
    # 1. Vértices de unión: donde concurren más de dos aristas distintas.
    incid = collections.defaultdict(set)
    for f in features:
        for poli in anillos(f.get('geometry')):
            for ring in poli:
                for a, b in zip(ring, ring[1:]):
                    ta, tb = tuple(a), tuple(b)
                    incid[ta].add(tb); incid[tb].add(ta)
    union = {v for v, vec in incid.items() if len(vec) != 2}

    cache = {}

    def simplifica_anillo(ring):
        pts = [tuple(c) for c in ring]
        cortes = [i for i, p in enumerate(pts[:-1]) if p in union]
        if not cortes:                       # anillo aislado: se simplifica entero
            salida = _dp(pts[:-1] + [pts[0]], tol)
            return salida if len(salida) > 3 else pts
        # rotar para empezar en un vértice de unión
        k = cortes[0]
        seq = pts[k:-1] + pts[:k + 1]
        cortes = [i for i, p in enumerate(seq) if p in union]
        nuevo = []
        for ini, fin in zip(cortes, cortes[1:]):
            arco = seq[ini:fin + 1]
            clave = min(tuple(arco), tuple(reversed(arco)))
            if clave not in cache:
                cache[clave] = _dp(list(clave), tol)
            simp = cache[clave]
            if tuple(arco) != clave:
                simp = list(reversed(simp))
            nuevo.extend(simp[:-1])
        nuevo.append(nuevo[0])
        return nuevo if len(nuevo) > 3 else pts

    for f in features:
        g = f.get('geometry')
        if not g:
            continue
        polis = anillos(g)
        nuevas = [[[list(c) for c in simplifica_anillo(r)] for r in poli] for poli in polis]
        if g['type'] == 'Polygon':
            g['coordinates'] = nuevas[0]
        else:
            g['coordinates'] = nuevas


def redondear(geom, p=PRECISION):
    def r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], p), round(c[1], p)]
        return [r(x) for x in c]
    return {'type': geom['type'], 'coordinates': r(geom['coordinates'])}


def disolver(geoms):
    """
    Une polígonos adyacentes cancelando las aristas que aparecen dos veces.
    Requiere topología limpia (vértices compartidos exactos), que es el caso
    de los límites del INEI. Devuelve una lista de anillos.
    """
    cuenta = collections.Counter()
    for g in geoms:
        for poly in anillos(g):
            for ring in poly:
                for a, b in zip(ring, ring[1:]):
                    cuenta[frozenset([tuple(a), tuple(b)])] += 1

    ady = collections.defaultdict(list)
    for g in geoms:
        for poly in anillos(g):
            for ring in poly:
                for a, b in zip(ring, ring[1:]):
                    a, b = tuple(a), tuple(b)
                    if cuenta[frozenset([a, b])] == 1:   # arista de borde exterior
                        ady[a].append(b)
                        ady[b].append(a)

    def siguiente(prev, cur):
        """En un vértice donde concurren más de dos aristas de borde, seguir 'la
        siguiente en rotación' — el giro más cerrado a la izquierda. Elegir al azar
        parte el contorno en dos anillos y deja huecos falsos entre zonas vecinas."""
        opciones = [v for v in ady[cur] if (cur, v) not in usados]
        if not opciones:
            return None
        if len(opciones) == 1:
            return opciones[0]
        base = math.atan2(prev[1] - cur[1], prev[0] - cur[0])
        def giro(v):
            a = math.atan2(v[1] - cur[1], v[0] - cur[0]) - base
            return a % (2 * math.pi)
        return min(opciones, key=giro)

    usados, salida = set(), []
    for inicio in list(ady):
        for sig in list(ady[inicio]):
            if (inicio, sig) in usados:
                continue
            ring = [inicio]
            prev, cur = inicio, sig
            usados.add((inicio, sig)); usados.add((sig, inicio))
            while cur != inicio:
                ring.append(cur)
                nxt = siguiente(prev, cur)
                if nxt is None:
                    break
                usados.add((cur, nxt)); usados.add((nxt, cur))
                prev, cur = cur, nxt
            ring.append(inicio)
            if len(ring) > 3:
                salida.append([list(c) for c in ring])
    return salida


def a_geometria(lista_anillos):
    """Convierte anillos sueltos en Polygon o MultiPolygon (cada anillo = un polígono)."""
    if len(lista_anillos) == 1:
        return {'type': 'Polygon', 'coordinates': [lista_anillos[0]]}
    return {'type': 'MultiPolygon', 'coordinates': [[r] for r in lista_anillos]}


def titulo(s):
    """AMAZONAS -> Amazonas, respetando preposiciones."""
    menores = {'de', 'del', 'la', 'las', 'los', 'y', 'en'}
    palabras = s.strip().lower().split()
    return ' '.join(w if i and w in menores else w.capitalize() for i, w in enumerate(palabras))


def normalizar(s):
    """Para emparejar nombres entre catálogos: sin tildes, sin dobles espacios, mayúsculas."""
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    return ' '.join(s.upper().replace('-', ' ').split())


# ───────────────────────── mapeo distrito → UGEL ─────────────────────────

def mapeo_desde_csv(ruta):
    """
    CSV con cabecera: ubigeo,cod_ugel,nom_ugel[,colegios]
    Si un ubigeo aparece varias veces, gana la UGEL con más colegios.
    """
    mejor = {}
    with open(ruta, encoding='utf-8-sig', newline='') as fh:
        for fila in csv.DictReader(fh):
            ubi = str(fila['ubigeo']).strip().zfill(6)
            n = int(fila.get('colegios') or 1)
            if ubi not in mejor or n > mejor[ubi][2]:
                mejor[ubi] = (str(fila['cod_ugel']).strip(), fila.get('nom_ugel', '').strip(), n)
    return {u: (c, n) for u, (c, n, _) in mejor.items()}


def mapeo_desde_sql(cadena_conexion, consulta):
    import pyodbc
    mejor = {}
    with pyodbc.connect(cadena_conexion) as cn:
        for ubi, cod, nom, cant in cn.cursor().execute(consulta):
            ubi = str(ubi).strip().zfill(6)
            cant = int(cant or 1)
            if ubi not in mejor or cant > mejor[ubi][2]:
                mejor[ubi] = (str(cod).strip(), (nom or '').strip(), cant)
    return {u: (c, n) for u, (c, n, _) in mejor.items()}


CONSULTA_SQL = """
-- Distrito -> UGEL, decidido por el número de instituciones educativas.
-- Ajusta nombres de tabla/columna a tu esquema.
SELECT  ubigeo, cod_ugel, MAX(nom_ugel) AS nom_ugel, COUNT(*) AS colegios
FROM (
    SELECT  RIGHT('000000' + CAST(s.COD_UBIGEO_DISTRITO AS VARCHAR(6)), 6) AS ubigeo,
            LTRIM(RTRIM(s.COD_UGEL))                                        AS cod_ugel,
            LTRIM(RTRIM(u.NOM_UGEL))                                        AS nom_ugel
    FROM    servicio.unidad_servicio_educativo_sgp s
    JOIN    dbo.catalogo_ugel u ON u.COD_UGEL = s.COD_UGEL
    WHERE   s.ESTADO = 1
) t
GROUP BY ubigeo, cod_ugel;
"""


# ───────────────────────── construcción de capas ─────────────────────────

def construir(args):
    os.makedirs(args.salida, exist_ok=True)

    dist = json.load(open(args.distritos, encoding='utf-8'))

    if args.simplificar:
        antes = sum(len(r) for f in dist['features'] for p in anillos(f.get('geometry')) for r in p)
        simplificar_topologico(dist['features'], args.simplificar)
        ahora = sum(len(r) for f in dist['features'] for p in anillos(f.get('geometry')) for r in p)
        print(f'  simplificado: {antes:,} -> {ahora:,} vértices '
              f'({100 - 100 * ahora / antes:.0f} % menos, tolerancia {args.simplificar})')

    # --- regiones: se disuelven desde los distritos, NO se toman de un archivo aparte.
    # Es lo que garantiza que el contorno regional calce exactamente con los bordes de
    # UGEL y de distrito al superponer las capas.
    por_region, nombre_region = collections.defaultdict(list), {}
    for f in dist['features']:
        if not f.get('geometry'):
            continue
        p = f['properties']
        por_region[p['IDDPTO']].append(f['geometry'])
        nombre_region[p['IDDPTO']] = titulo(p['NOMBDEP'])

    regiones = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature',
         'properties': {'codigo': cod, 'nombre': nombre_region[cod]},
         'geometry': redondear(a_geometria(disolver(geoms)))}
        for cod, geoms in sorted(por_region.items())
    ]}
    escribir(os.path.join(args.salida, 'peru-regiones.json'), regiones)

    # --- distritos ---
    distritos = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature',
         'properties': {'ubigeo': f['properties']['IDDIST'],
                        'nombre': titulo(f['properties']['NOMBDIST']),
                        'region': f['properties']['IDDPTO']},
         'geometry': redondear(f['geometry'])}
        for f in dist['features'] if f.get('geometry')
    ]}
    escribir(os.path.join(args.salida, 'peru-distritos.json'), distritos)

    sin_geo = [f['properties']['IDDIST'] for f in dist['features'] if not f.get('geometry')]
    if sin_geo:
        print(f'  aviso: {len(sin_geo)} distritos sin polígono en la fuente: {", ".join(sin_geo)}')

    # --- UGEL ---
    if args.mapeo_csv:
        mapa = mapeo_desde_csv(args.mapeo_csv)
        origen = f'mapeo real ({len(mapa)} distritos)'
    elif args.conexion:
        mapa = mapeo_desde_sql(args.conexion, CONSULTA_SQL)
        origen = f'SQL Server ({len(mapa)} distritos)'
    else:
        mapa = None
        origen = 'aproximación por provincia'

    grupos, nombres = collections.defaultdict(list), {}
    regiones_de = collections.defaultdict(collections.Counter)
    sin_mapear, pendientes = [], set()
    for f in dist['features']:
        g = f.get('geometry')
        if not g:
            continue
        p = f['properties']
        par = mapa.get(p['IDDIST']) if mapa else None
        if par:
            clave, nombre = par
        elif mapa and args.solo_mapeo:
            sin_mapear.append(p['IDDIST'])
            continue
        else:
            # El mapeo puede ser parcial: lo no cubierto cae al proxy de provincia,
            # así puedes ir verificando una región a la vez.
            clave, nombre = p['IDPROV'], ('' if mapa else 'UGEL ') + titulo(p['NOMBPROV'])
            if mapa:
                sin_mapear.append(p['IDDIST'])
                pendientes.add(clave)
        grupos[clave].append(g)
        nombres[clave] = nombre
        regiones_de[clave][p['IDDPTO']] += 1

    feats = []
    for clave, geoms in sorted(grupos.items()):
        rs = disolver(geoms)
        if not rs:
            print(f'  aviso: no se pudo disolver {clave} ({nombres[clave]})')
            continue
        feats.append({'type': 'Feature',
                      'properties': {'codigo': clave, 'nombre': nombres[clave],
                                     # Una UGEL puede cruzar provincias; la región es la
                                     # mayoritaria entre sus distritos.
                                     'region': regiones_de[clave].most_common(1)[0][0],
                                     'distritos': len(geoms),
                                     # pendiente = polígono provincial de relleno: la
                                     # jurisdicción UGEL de esa zona aún no está resuelta.
                                     'pendiente': clave in pendientes},
                      'geometry': redondear(a_geometria(rs))})

    escribir(os.path.join(args.salida, 'peru-ugel.json'),
             {'type': 'FeatureCollection', 'features': feats})
    print(f'  UGEL: {len(feats)} polígonos — {origen}')
    if sin_mapear:
        destino = 'quedan fuera del mapa' if args.solo_mapeo else 'caen al proxy de provincia'
        print(f'  aviso: {len(sin_mapear)} distritos no cubiertos por el mapeo ({destino})')


def escribir(ruta, obj):
    with open(ruta, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(',', ':'))
    kb = os.path.getsize(ruta) / 1024
    print(f'  {os.path.basename(ruta):24s} {len(obj["features"]):5d} features  {kb:7.0f} KB')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Genera las capas GeoJSON para PeruMap')
    ap.add_argument('--distritos', default='peru_distrital_simple.geojson')
    ap.add_argument('--salida', default='data')
    ap.add_argument('--simplificar', type=float, default=0.0,
                    help='tolerancia en grados (0.002 ~ 200 m). 0 = sin simplificar. '
                         'Respeta la topología: los bordes compartidos quedan idénticos.')
    ap.add_argument('--solo-mapeo', action='store_true',
                    help='Descarta los distritos que el mapeo no cubre, en vez de usar el proxy de provincia')
    ap.add_argument('--mapeo-csv', help='CSV ubigeo,cod_ugel,nom_ugel[,colegios]')
    ap.add_argument('--conexion', help='Cadena ODBC; usa CONSULTA_SQL para leer el mapeo')
    args = ap.parse_args()
    print('Generando capas...')
    construir(args)
    print('Listo.')

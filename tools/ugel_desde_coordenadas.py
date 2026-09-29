#!/usr/bin/env python3
"""
ugel_desde_coordenadas.py — deduce qué UGEL administra cada distrito a partir de las
coordenadas de los colegios.

Es la forma de resolver una UGEL sub-provincial sin tener su resolución de creación:
se ubica cada colegio en su distrito por punto-en-polígono y gana la UGEL con más
colegios en ese distrito.

Entrada: CSV sin cabecera, separado por ';'
    cod_dre;nom_dre;cod_ugel;nom_ugel;cod_modular;latitud;longitud

Salida: un data/ugel-<nombre>.csv con ubigeo,cod_ugel,nom_ugel listo para
        preparar_escale.py, más un informe de los distritos repartidos entre dos UGEL.

Uso:
    python tools/ugel_desde_coordenadas.py BAGUA_IMAZA.csv \\
        --distritos peru_distrital_simple.geojson --nombre bagua

Sin dependencias externas: solo stdlib.
"""

import argparse, collections, csv, json, os

# Perú continental, para descartar coordenadas corruptas o invertidas.
LIMITES = (-82.0, -0.02, -68.6, -18.4)   # oeste, norte, este, sur


def en_anillo(x, y, anillo):
    """Cruce de rayos: cuenta cuántas aristas cruza una semirrecta horizontal."""
    adentro = False
    j = len(anillo) - 1
    for i in range(len(anillo)):
        xi, yi = anillo[i]
        xj, yj = anillo[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            adentro = not adentro
        j = i
    return adentro


def en_geometria(x, y, geom):
    polis = [geom['coordinates']] if geom['type'] == 'Polygon' else geom['coordinates']
    for poli in polis:
        if en_anillo(x, y, poli[0]) and not any(en_anillo(x, y, h) for h in poli[1:]):
            return True
    return False


def main(args):
    dist = json.load(open(args.distritos, encoding='utf-8'))
    poligonos = [f for f in dist['features'] if f.get('geometry')]

    # Se deduplica por (UGEL, código modular): al juntar varios archivos es fácil
    # repetir colegios, y un lado duplicado gana comparaciones que no le tocan.
    filas, vistos, repetidos = [], set(), 0
    with open(args.entrada, encoding='utf-8-sig', newline='') as fh:
        for r in csv.reader(fh, delimiter=args.separador):
            if len(r) < 7:
                continue
            r = [x.strip() for x in r]
            clave = (r[2].zfill(6), r[4])
            if clave in vistos:
                repetidos += 1
                continue
            vistos.add(clave)
            filas.append(r)
    if repetidos:
        print(f'  filas duplicadas descartadas: {repetidos}')

    # Solo se recorren los distritos de las regiones presentes en el archivo:
    # evita cruzar 524 puntos contra 1826 polígonos.
    regiones = {r[2].strip().zfill(6)[:2] for r in filas}
    candidatos = [f for f in poligonos if f['properties']['IDDPTO'] in regiones]

    nombres = {}
    votos = collections.defaultdict(collections.Counter)
    descartados = collections.Counter()

    for _, _, cod_ugel, nom_ugel, _, lat, lon in filas:
        cod_ugel = cod_ugel.zfill(6)
        nombres[cod_ugel] = nom_ugel
        try:
            x, y = float(lon), float(lat)
        except ValueError:
            descartados['coordenada ilegible'] += 1
            continue
        if not (LIMITES[0] < x < LIMITES[2] and LIMITES[3] < y < LIMITES[1]):
            descartados['fuera del Perú'] += 1
            continue
        hit = next((f for f in candidatos if en_geometria(x, y, f['geometry'])), None)
        if hit:
            votos[hit['properties']['IDDIST']][cod_ugel] += 1
        else:
            descartados['sin distrito (zona sin polígono)'] += 1

    info = {f['properties']['IDDIST']: (f['properties']['NOMBDIST'], f['properties']['NOMBPROV'])
            for f in candidatos}

    print(f'  colegios leídos     {len(filas)}')
    for k, v in descartados.items():
        print(f'  descartados         {v}  ({k})')
    print(f'  distritos con datos {len(votos)}\n')

    salida, repartidos, debiles, mal = [], [], [], 0
    for ubigeo, c in sorted(votos.items()):
        total = sum(c.values())
        ganadora, n = c.most_common(1)[0]
        # Si el archivo solo trae algunas UGEL, un puñado de colegios sueltos NO prueba
        # que la UGEL administre el distrito: puede ser ruido de coordenadas o una
        # jurisdicción compartida cuya contraparte no está en los datos. Ante la duda,
        # el distrito se deja como está.
        if n < args.minimo:
            debiles.append((ubigeo, info[ubigeo], c))
            continue
        mal += total - n
        salida.append((ubigeo, ganadora, nombres[ganadora]))
        detalle = '  '.join(f'{nombres[k].replace("UGEL ", "")}:{v}' for k, v in c.most_common())
        marca = ''
        if len(c) > 1 and (total - n) / total >= args.umbral:
            repartidos.append((ubigeo, info[ubigeo][0], c, total - n))
            marca = '  ← REPARTIDO'
        print(f'  {ubigeo} {info[ubigeo][0][:20]:20s} {info[ubigeo][1][:13]:13s} {total:4d}  {detalle}{marca}')

    ruta = os.path.join(args.salida, f'ugel-{args.nombre}.csv')
    with open(ruta, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['ubigeo', 'cod_ugel', 'nom_ugel'])
        w.writerows(salida)

    if debiles:
        print(f'\n  Evidencia insuficiente (menos de {args.minimo} colegios): {len(debiles)} distritos')
        print('  NO se asignan. Revísalos: pueden ser errores de coordenada o zonas compartidas.')
        for ubigeo, (nom, prov) in [(u, i) for u, i, _ in debiles]:
            c = dict(next(cc for uu, _, cc in debiles if uu == ubigeo))
            det = ' '.join(f'{nombres[k].replace("UGEL ", "")}:{v}' for k, v in c.items())
            print(f'    {ubigeo} {nom[:20]:20s} {prov[:14]:14s} {det}')

    print(f'\n  {ruta}: {len(salida)} distritos')
    print(f'  colegios que la asignación por distrito deja en la UGEL equivocada: '
          f'{mal} de {sum(sum(c.values()) for c in votos.values())}')
    if repartidos:
        print('\n  Distritos repartidos entre dos UGEL. El polígono distrital no puede')
        print('  representarlos: la mayoría se lleva el distrito entero.')
        for ubigeo, nom, c, perdidos in repartidos:
            print(f'    {ubigeo} {nom}: {perdidos} colegios quedan mal asignados')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Deduce el mapeo distrito→UGEL desde coordenadas')
    ap.add_argument('entrada', help='CSV de colegios con lat/lon')
    ap.add_argument('--distritos', default='peru_distrital_simple.geojson')
    ap.add_argument('--salida', default='data')
    ap.add_argument('--nombre', required=True, help='sufijo del archivo: data/ugel-<nombre>.csv')
    ap.add_argument('--separador', default=';')
    ap.add_argument('--minimo', type=int, default=10,
                    help='colegios mínimos de la UGEL ganadora para asignarle el distrito')
    ap.add_argument('--umbral', type=float, default=0.10,
                    help='proporción mínima de la minoría para reportar un distrito repartido')
    print('Ubicando colegios en su distrito...')
    main(ap.parse_args())
    print('Listo.')

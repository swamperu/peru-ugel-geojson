#!/usr/bin/env python3
"""
listar_no_mapeados.py — muestra qué distritos de la capa geográfica no tienen UGEL.

Cada uno de estos sale como un polígono gris en el mapa. Aparecen sobre todo al cambiar
a una versión más reciente del INEI, que incluye distritos creados después del mapeo.

Uso:
    python tools/listar_no_mapeados.py distritos_inei.geojson --mapeo data/ugel-distrito.csv
    python tools/listar_no_mapeados.py distritos_inei.geojson --mapeo data/ugel-distrito.csv --csv nuevos.csv
"""

import argparse, collections, csv, json


def main(args):
    mapeados = {r['ubigeo'].strip().zfill(6)
                for r in csv.DictReader(open(args.mapeo, encoding='utf-8-sig'))}
    dist = json.load(open(args.geojson, encoding='utf-8'))

    # Para cada provincia, qué UGEL tienen ya sus distritos: casi siempre el distrito
    # nuevo hereda la UGEL de la provincia de la que se desprendió.
    ugel_de = {r['ubigeo'].strip().zfill(6): (r['cod_ugel'].strip(), r.get('nom_ugel', '').strip())
               for r in csv.DictReader(open(args.mapeo, encoding='utf-8-sig'))}
    por_prov = collections.defaultdict(collections.Counter)
    for f in dist['features']:
        u = f['properties'].get('IDDIST', '')
        if u in ugel_de:
            por_prov[u[:4]][ugel_de[u]] += 1

    faltan = []
    for f in dist['features']:
        p = f['properties']
        u = p.get('IDDIST', '')
        if u and u not in mapeados:
            sugerida = por_prov[u[:4]].most_common(1)
            faltan.append((u, p.get('NOMBDIST', ''), p.get('NOMBPROV', ''), p.get('NOMBDEP', ''),
                           sugerida[0][0] if sugerida else ('', ''),
                           len(por_prov[u[:4]])))

    print(f'  distritos en la capa: {len(dist["features"])}')
    print(f'  sin UGEL asignada:    {len(faltan)}\n')
    for u, nd, np_, ndep, (cod, nom), n_ugel in sorted(faltan):
        aviso = '' if n_ugel <= 1 else f'  ← ¡su provincia tiene {n_ugel} UGEL, verificar!'
        print(f'  {u} {nd[:24]:24s} {np_[:16]:16s} {ndep[:14]:14s} -> {cod} {nom[:26]}{aviso}')

    if args.csv:
        with open(args.csv, 'w', encoding='utf-8', newline='') as fh:
            w = csv.writer(fh); w.writerow(['ubigeo', 'cod_ugel', 'nom_ugel'])
            for u, _, _, _, (cod, nom), _ in sorted(faltan):
                if cod:
                    w.writerow([u, cod, nom])
        print(f'\n  {args.csv} generado con la UGEL mayoritaria de cada provincia.')
        print('  REVÍSALO: las líneas marcadas son suposiciones, no datos. Por eso')
        print('  preparar_escale.py ignora los archivos con "nuevos" en el nombre: este')
        print('  archivo no se aplica solo. Verifica cada línea y guárdala con otro nombre,')
        print('  o resuélvelas con tools/ugel_desde_coordenadas.py si tienes lat/lon.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Lista los distritos sin UGEL asignada')
    ap.add_argument('geojson')
    ap.add_argument('--mapeo', default='data/ugel-distrito.csv')
    ap.add_argument('--csv', help='escribe un CSV con la UGEL sugerida por provincia')
    main(ap.parse_args())

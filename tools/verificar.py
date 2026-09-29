#!/usr/bin/env python3
"""
verificar.py — revisa que los archivos de data/ sean consistentes entre sí.

Correr SIEMPRE después de regenerar. Detecta el error más común: capas y datos
producidos en corridas distintas, que hace que ningún polígono encuentre su cifra
y el mapa salga entero en gris.

Uso:  python tools/verificar.py            (o --salida otra_carpeta)
"""

import argparse, json, os, sys


def cargar(carpeta, nombre):
    ruta = os.path.join(carpeta, nombre)
    if not os.path.exists(ruta):
        return None, f'FALTA {nombre}'
    try:
        return json.load(open(ruta, encoding='utf-8')), None
    except Exception as e:
        return None, f'{nombre} ilegible: {e}'


def main(args):
    problemas, avisos = [], []
    d = args.salida

    regiones, err = cargar(d, 'peru-regiones.json');  problemas += [err] if err else []
    ugel, err = cargar(d, 'peru-ugel.json');          problemas += [err] if err else []
    escale, err = cargar(d, 'escale-colegios.json');  problemas += [err] if err else []
    if problemas:
        print('\n'.join('  ✗ ' + p for p in problemas)); sys.exit(1)

    # --- tamaños ---
    for nombre in ('peru-regiones.json', 'peru-ugel.json', 'peru-distritos.json'):
        ruta = os.path.join(d, nombre)
        if os.path.exists(ruta):
            kb = os.path.getsize(ruta) / 1024
            marca = '  ← DEMASIADO PESADO: te falta --simplificar' if kb > 2000 else ''
            print(f'  {nombre:22s} {kb:8.0f} KB{marca}')
            if kb > 2000:
                problemas.append(f'{nombre} pesa {kb/1024:.0f} MB')

    # --- cruce UGEL ---
    cod_geo = {f['properties']['codigo'] for f in ugel['features']}
    cod_dat = set(escale['ugel'])
    sin_dato = cod_geo - cod_dat
    sin_mapa = cod_dat - cod_geo
    print(f'\n  polígonos UGEL:       {len(cod_geo)}')
    print(f'  UGEL con cifras:      {len(cod_dat)}')
    print(f'  polígonos sin dato:   {len(sin_dato)}')
    print(f'  UGEL sin polígono:    {len(sin_mapa)}')

    if len(sin_dato) > len(cod_geo) * 0.5:
        problemas.append('más de la mitad de los polígonos no encuentra su dato: '
                         'las capas y escale-colegios.json son de corridas distintas')
    elif sin_dato:
        avisos.append('sin dato: ' + ', '.join(sorted(sin_dato)[:12]))
    if sin_mapa:
        avisos.append('sin polígono: ' + ', '.join(sorted(sin_mapa)[:12]))

    # --- cruce regiones ---
    reg_geo = {f['properties']['codigo'] for f in regiones['features']}
    faltan_reg = reg_geo - set(escale['region'])
    if faltan_reg:
        problemas.append(f'regiones sin cifras: {sorted(faltan_reg)}')

    # --- topología entre capas ---
    def vertices(fc):
        s = set()
        for f in fc['features']:
            g = f['geometry']
            polis = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
            for p in polis:
                for r in p:
                    s.update(tuple(c) for c in r)
        return s

    sueltos = vertices(regiones) - vertices(ugel)
    print(f'  vértices de región ausentes en la capa UGEL: {len(sueltos)}')
    if sueltos:
        problemas.append('las capas no comparten vértices: se van a dibujar bordes dobles. '
                         'Regenera ambas desde el MISMO archivo distrital.')

    print()
    for a in avisos:
        print('  aviso: ' + a)
    for p in problemas:
        print('  ✗ ' + p)
    if not problemas:
        print('  ✓ todo consistente')
    sys.exit(1 if problemas else 0)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Verifica la consistencia de data/')
    ap.add_argument('--salida', default='data')
    main(ap.parse_args())

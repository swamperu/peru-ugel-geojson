#!/usr/bin/env python3
"""
preparar_escale.py — cruza el padrón de UGEL de ESCALE con la geometría distrital.

Entrada:
    DATA_ESCALE.csv          cod_dre;nom_dre;cod_ugel;nom_ugel;nivel;area;colegios  (sin cabecera)
    peru_distrital_simple.geojson

Salidas en data/:
    ugel-distrito.csv        ubigeo -> cod_ugel  (el mapeo que consume construir_geometria.py)
    ugel-catalogo.csv        las 226 UGEL con su código oficial y cómo se resolvió cada una
    escale-colegios.json     agregados por UGEL y por región, listos para el mapa

Cómo se resuelve cada UGEL:
    1. por nombre exacto contra la provincia de su misma región
    2. por ortografía cercana (Nasca/Nazca, Vilcashuamán/Vilcas Huamán), rechazando
       calificativos como NORTE, SUR o ALTO, que delatan una porción de provincia
    3. por un mapeo distrital manual (data/ugel-*.csv), como el de Lima Metropolitana
    Lo que no se resuelve queda marcado como pendiente: nunca se inventa una jurisdicción.
"""

import argparse, collections, csv, difflib, json, os, re, unicodedata

CALIFICATIVOS = {'NORTE', 'SUR', 'ESTE', 'OESTE', 'NOR', 'ALTO', 'BAJO',
                 'INTERCULTURAL', 'BILINGUE'}

# Palabras que describen la modalidad, no el territorio: estorban al buscar el distrito sede.
RUIDO = {'INTERCULTURAL', 'BILINGUE', 'DE', 'DEL', 'LA', 'EL', 'LOS', 'LAS'}


def variantes_distrito(nombre):
    """Formas en que el nombre de una UGEL puede aludir a su distrito sede.
    'UGEL IBIR-IMAZA' -> IBIR IMAZA, IBIR, IMAZA. 'UGEL INTERCULTURAL BILINGÜE CENEPA'
    -> CENEPA. Se prueban todos los tramos del guion, no solo el primero."""
    b = norm(nombre)
    b = re.sub(r'^UGEL\s+', '', b)
    b = re.sub(r'^DIRECCION REGIONAL DE EDUCACION\s+', '', b)
    b = re.sub(r'^\d+\s+', '', b)
    out = []
    for tramo in [b] + [t for t in b.replace('-', ' - ').split(' - ')]:
        t = ' '.join(tramo.replace('-', ' ').split())
        limpio = ' '.join(w for w in t.split() if w not in RUIDO)
        for cand in (t, limpio):
            if cand and cand not in out:
                out.append(cand)
    return out


def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    return ' '.join(s.upper().replace('.', ' ').split())


def variantes(nombre):
    """Formas comparables de un nombre de UGEL: sin prefijo, sin numeral, y el tramo
    anterior al guion ('UGEL LORETO - NAUTA' -> 'LORETO')."""
    b = norm(nombre).replace('-', ' - ')
    b = re.sub(r'^UGEL\s+', '', b)
    b = re.sub(r'^DIRECCION REGIONAL DE EDUCACION\s+', '', b)
    b = re.sub(r'^\d+\s+', '', b)
    v = [' '.join(b.replace('-', ' ').split())]
    if ' - ' in b:
        v.append(' '.join(b.split(' - ')[0].split()))
    return v


def leer_escale(ruta):
    ugel, agg = {}, collections.defaultdict(collections.Counter)
    with open(ruta, encoding='utf-8-sig', newline='') as fh:
        for fila in csv.reader(fh, delimiter=';'):
            if len(fila) < 7:
                continue
            cod_dre, nom_dre, cod_ugel, nom_ugel, nivel, area, n = [x.strip() for x in fila]
            cod_ugel = cod_ugel.zfill(6)        # Excel se come el cero inicial de Amazonas
            ugel[cod_ugel] = (nom_ugel, nom_dre)
            a = agg[cod_ugel]
            a['total'] += int(n)
            a[nivel.replace('EBR ', '').lower()] += int(n)
            a[area.lower()] += int(n)
    return ugel, agg


# Sufijos de archivos de trabajo: salidas de prueba o borradores que NO son mapeo
# verificado. Se ignoran para que un archivo olvidado en data/ no pise el trabajo bueno.
# 'nuevos' cubre ugel-nuevos.csv, la salida de listar_no_mapeados.py: son UGEL SUGERIDAS
# por provincia, no verificadas, y nunca deben consumirse sin revisar antes.
DESCARTAR = ('prueba', 'test', 'tmp', 'temp', 'borrador', 'backup', 'copia', 'old', 'nuevos')


def leer_mapeos_manuales(carpeta):
    """Lee los data/ugel-*.csv con mapeo distrital verificado a mano."""
    manual = {}
    print('  mapeos leídos:')
    # 'correcciones' se lee al final para que sus líneas ganen sobre las demás.
    archivos = sorted(os.listdir(carpeta), key=lambda n: ('correcciones' in n, n))
    for nombre in archivos:
        if not (nombre.startswith('ugel-') and nombre.endswith('.csv')):
            continue
        if nombre in ('ugel-distrito.csv', 'ugel-catalogo.csv'):
            continue
        if any(x in nombre.lower() for x in DESCARTAR):
            print(f'    IGNORADO {nombre}  (parece archivo de trabajo, no mapeo verificado)')
            continue
        n_antes = len(manual)
        with open(os.path.join(carpeta, nombre), encoding='utf-8-sig', newline='') as fh:
            for fila in csv.DictReader(fh):
                ubi = fila['ubigeo'].strip().zfill(6)
                cod = fila['cod_ugel'].strip().zfill(6)
                if ubi in manual and manual[ubi] != cod:
                    print(f'  CONFLICTO: el distrito {ubi} está asignado a {manual[ubi]} '
                          f'y también a {cod} en {nombre}')
                manual[ubi] = cod
        print(f'    {nombre:32s} {len(manual) - n_antes:+4d} distritos')
    return manual


def main(args):
    ugel, agg = leer_escale(args.escale)
    dist = json.load(open(args.distritos, encoding='utf-8'))

    provincias = collections.defaultdict(dict)
    distritos_de = collections.defaultdict(list)
    nombre_prov = {}
    for f in dist['features']:
        p = f['properties']
        provincias[p['IDDPTO']][norm(p['NOMBPROV'])] = p['IDPROV']
        distritos_de[p['IDPROV']].append(p['IDDIST'])
        nombre_prov[p['IDPROV']] = p['NOMBPROV']

    manual = leer_mapeos_manuales(args.salida)
    con_manual = {cod for cod in manual.values()}

    asignada, metodo = {}, {}
    for cod, (nom, _) in sorted(ugel.items()):
        cand = provincias.get(cod[:2], {})
        for v in variantes(nom):
            if v in cand:
                asignada[cod], metodo[cod] = cand[v], 'provincia'
                break
        else:
            for v in variantes(nom):
                m = difflib.get_close_matches(v, list(cand), n=1, cutoff=0.78)
                sobra = (set(v.split()) & CALIFICATIVOS) - set(m[0].split()) if m else None
                if m and not sobra:
                    asignada[cod], metodo[cod] = cand[m[0]], f'provincia~{nombre_prov[cand[m[0]]]}'
                    break
            else:
                metodo[cod] = 'pendiente'

    # Una provincia reclamada por dos UGEL significa que ninguna la cubre entera.
    repetida = collections.Counter(asignada.values())
    for cod, prov in list(asignada.items()):
        if repetida[prov] > 1:
            del asignada[cod]
            metodo[cod] = 'pendiente'

    # Una UGEL con mapeo distrital verificado NO depende del calce por provincia:
    # se marca al final para que el chequeo de provincia compartida no la degrade.
    for cod in con_manual:
        if cod in ugel:
            # Conserva su calce por provincia: el mapeo distrital solo corrige
            # distritos puntuales, no reemplaza la cobertura provincial.
            metodo[cod] = 'distrital'

    # Una UGEL sub-provincial sin resolver deja INFLADO el polígono de la UGEL que sí
    # calzó con esa provincia: le sobran los distritos que en realidad administra la otra.
    # Se localiza la provincia afectada por el nombre del distrito sede de la pendiente.
    distrito_en = collections.defaultdict(dict)
    prov_del_distrito = {}
    for f in dist['features']:
        p = f['properties']
        clave = norm(p['NOMBDIST'])
        distrito_en[p['IDDPTO']][clave] = p['IDDIST']
        # 'EL CENEPA' también indexado como 'CENEPA': las UGEL omiten el artículo.
        corto = ' '.join(w for w in clave.split() if w not in RUIDO)
        distrito_en[p['IDDPTO']].setdefault(corto or clave, p['IDDIST'])
        prov_del_distrito[p['IDDIST']] = p['IDPROV']

    provincias_tocadas = collections.defaultdict(list)
    for cod, m in metodo.items():
        if m != 'pendiente':
            continue
        cand = distrito_en.get(cod[:2], {})
        for v in variantes_distrito(ugel[cod][0]):
            elegido = cand.get(v)
            if not elegido:
                m = difflib.get_close_matches(v, list(cand), n=1, cutoff=0.86)
                elegido = cand[m[0]] if m else None
            if elegido:
                provincias_tocadas[prov_del_distrito[elegido]].append(ugel[cod][0])
                break

    for cod, prov in asignada.items():
        if prov in provincias_tocadas:
            metodo[cod] = 'provincia-revisar'

    # --- ugel-distrito.csv ---
    asignacion = {}
    for cod, prov in sorted(asignada.items()):
        for ubi in distritos_de[prov]:
            asignacion[ubi] = cod
    for ubi, cod in manual.items():            # el mapeo verificado pisa al provincial
        if cod in ugel:
            asignacion[ubi] = cod
    filas = [(ubi, cod, ugel[cod][0]) for ubi, cod in sorted(asignacion.items())]
    ruta = os.path.join(args.salida, 'ugel-distrito.csv')
    with open(ruta, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh); w.writerow(['ubigeo', 'cod_ugel', 'nom_ugel']); w.writerows(sorted(filas))

    # --- ugel-catalogo.csv ---
    ruta_cat = os.path.join(args.salida, 'ugel-catalogo.csv')
    with open(ruta_cat, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['cod_ugel', 'nom_ugel', 'dre', 'region', 'geometria', 'colegios'])
        for cod, (nom, dre) in sorted(ugel.items()):
            w.writerow([cod, nom, dre, cod[:2], metodo[cod], agg[cod]['total']])
    sin_ubicar = [u for us in provincias_tocadas.values() for u in us]

    # --- escale-colegios.json ---
    por_region = collections.defaultdict(collections.Counter)
    for cod, a in agg.items():
        por_region[cod[:2]].update(a)
    datos = {
        'fuente': 'ESCALE - MINEDU. Instituciones educativas de EBR por UGEL, nivel y área.',
        'nota_geometria': ('distrital = mapeo verificado · provincia = la UGEL cubre una '
                           'provincia entera · provincia-revisar = el polígono incluye zonas '
                           'de otra UGEL aún sin resolver · pendiente = sin polígono'),
        'ugel': {c: dict(a, nombre=ugel[c][0], dre=ugel[c][1], geometria=metodo[c])
                 for c, a in sorted(agg.items())},
        'region': {r: dict(a) for r, a in sorted(por_region.items())},
    }
    json.dump(datos, open(os.path.join(args.salida, 'escale-colegios.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))

    resueltas = sum(1 for m in metodo.values() if m != 'pendiente')
    cubiertos = sum(agg[c]['total'] for c, m in metodo.items() if m != 'pendiente')
    total = sum(a['total'] for a in agg.values())
    print(f'  UGEL en ESCALE          {len(ugel)}')
    print(f'  con geometría           {resueltas}  ({cubiertos:,} de {total:,} colegios)')
    print(f'  pendientes              {len(ugel) - resueltas}')
    print(f'  {os.path.basename(ruta)}: {len(filas)} distritos mapeados')
    revisar = sum(1 for m in metodo.values() if m == 'provincia-revisar')
    print(f'  polígonos inflados      {revisar}  (comparten provincia con una UGEL pendiente)')
    print(f'  provincias afectadas    {len(provincias_tocadas)}')
    for prov, us in sorted(provincias_tocadas.items()):
        print(f'    {prov} {nombre_prov[prov]:24s} <- {"; ".join(us)}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Cruza ESCALE con la geometría distrital')
    # Se acepta tanto suelto como con --escale: 'preparar_escale.py DATA.csv' funciona.
    ap.add_argument('escale_pos', nargs='?', help='CSV de ESCALE (también admite --escale)')
    ap.add_argument('--escale', default='DATA_ESCALE.csv')
    ap.add_argument('--distritos', default='peru_distrital_simple.geojson')
    ap.add_argument('--salida', default='data')
    args = ap.parse_args()
    if args.escale_pos:
        args.escale = args.escale_pos
    print('Cruzando ESCALE con la geometría...')
    main(args)
    print('Listo.')

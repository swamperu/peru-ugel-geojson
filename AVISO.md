# Aviso de uso y limitaciones

Léelo antes de usar estos datos para algo que importe.

## Qué es este proyecto

Un conjunto de **polígonos aproximados** que representan el ámbito territorial de las 226
UGEL del Perú, construidos a partir de datos públicos. Es un proyecto **independiente**, sin
vínculo con el MINEDU, las DRE, las UGEL ni ninguna entidad del Estado.

## Qué NO es

- **No es cartografía oficial.** Ninguna autoridad ha aprobado, validado ni revisado estos
  polígonos.
- **No es un instrumento de demarcación territorial.** No define ni modifica límites de
  ningún tipo.
- **No determina a qué UGEL pertenece una institución educativa.** Si necesitas saber eso con
  certeza, consulta el padrón de ESCALE del MINEDU, o directamente a la UGEL o DRE
  correspondiente. Ese dato es el que manda, no este mapa.
- **No sirve como sustento para actos administrativos**: procesos de racionalización,
  asignación de plazas, trámites, contrataciones o cualquier decisión con efecto sobre
  personas o instituciones.

Sirve para visualizar, explorar y analizar. Nada más, y ya es bastante.

## Por qué los polígonos son aproximados

### 1. No existe un mapa oficial de jurisdicciones UGEL

El Estado publica el padrón de qué UGEL administra cada colegio, pero **no publica los
límites geográficos de cada UGEL**. Este proyecto los construye: agrupa los distritos que
administra cada UGEL y disuelve sus fronteras internas.

### 2. Los límites distritales de base son referenciales

Se usan los límites censales del INEI, que el propio INEI clasifica como **referenciales, no
demarcatorios**. El MINEDU lo advierte en su visor SIGMED: los límites político-administrativos
son referenciales, se usan con fines cartográficos y *no determinan pertenencia oficial de una
institución educativa a una jurisdicción*.

### 3. Una UGEL no siempre respeta los límites distritales

Esta es la limitación de fondo, y conviene entenderla bien.

El polígono de cada UGEL se arma con **distritos completos**. Pero hay distritos donde
conviven colegios de dos UGEL distintas. Como un distrito no se puede partir, el distrito
entero se asigna a la UGEL que tiene más colegios ahí, y los de la otra quedan, en el mapa,
dentro del polígono equivocado.

**Cuánto pesa esto, medido:** sobre 16 540 colegios con coordenadas verificadas, **92,8 %
cae dentro del polígono de su propia UGEL y 7,2 % no**. Hay **96 distritos repartidos** entre
dos o más UGEL. Los más afectados son Mazamari, Río Tambo, Monzón, San Miguel de El Faique,
Pangoa y Trujillo.

La muestra verificada se concentra en las zonas más conflictivas, así que 92,8 % es más bien
un piso que un promedio.

## Cómo se construyó cada UGEL

El archivo [`data/ugel-catalogo.csv`](data/ugel-catalogo.csv) declara, UGEL por UGEL, de dónde
salió su polígono:

| Método | UGEL | Qué significa |
|---|---|---|
| `distrital` | 59 | La lista de distritos se verificó una por una, contra el organigrama oficial o ubicando los colegios por sus coordenadas. |
| `provincia` | 167 | La UGEL cubre una provincia completa y el polígono es el de esa provincia. |

Ninguna UGEL está marcada como dudosa: las que antes lo estaban se resolvieron con datos.

## Fuentes

- **Límites distritales**: límites censales del INEI, geoportal `ide.inei.gob.pe`.
- **Instituciones educativas y catálogo de UGEL**: ESCALE – MINEDU (`escale.minedu.gob.pe`).
- **Jurisdicción distrito → UGEL**: derivada de la ubicación de los colegios del padrón y de
  organigramas públicos de las DRE.

Las cifras son una **instantánea**, no un servicio en vivo. Verifica siempre contra la fuente
original antes de citarlas.

## Encontraste un error

Es probable que haya varios, sobre todo en zonas de selva y en los distritos repartidos. Si
conoces una jurisdicción de primera mano y el mapa la muestra mal, **abre un issue** indicando
la UGEL, los distritos que le corresponden y en qué te basas. Se corrige y se vuelve a
publicar: el proceso es reproducible y está documentado en el README.

## Sin garantías

Estos datos se ofrecen tal como están, sin garantía de exactitud, vigencia ni aptitud para
ningún propósito. Quien los use asume la responsabilidad de verificarlos. El autor no responde
por decisiones tomadas a partir de este material.

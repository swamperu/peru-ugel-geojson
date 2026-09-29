/**
 * PeruMap — mapa coroplético del Perú (regiones / provincias / UGEL)
 * Sin dependencias. Renderiza SVG a partir de GeoJSON y une con datos por código.
 *
 * Uso mínimo:
 *   const mapa = new PeruMap('#mapa', { formatoValor: v => v.toLocaleString('es-PE') });
 *   await mapa.cargarGeografia(geojson, { campoId: 'ubigeo', campoNombre: 'nombre' });
 *   mapa.setDatos([{ id: '01', valor: 1234 }]);
 *
 * @version 1.0.0
 */

const PALETAS = {
  // Secuenciales pensadas para fondo claro, seguras para deuteranopía.
  teal:    ['#e0f0ef', '#b4dbd8', '#7cc0bd', '#42a09d', '#1d7a78', '#0d5553'],
  indigo:  ['#e6e9f5', '#c2c9e8', '#959fd6', '#6a75bd', '#48509b', '#2d3372'],
  ambar:   ['#fdefd9', '#f8d9a6', '#f0bd6b', '#e09b34', '#bd7716', '#8c5407'],
  // Divergente: útil para brechas (déficit / superávit de plazas).
  brecha:  ['#a8322d', '#cd6b5f', '#e6a99c', '#dfe3e6', '#93b8c9', '#4b87a6', '#1d5a7a'],
};

const COLOR_SIN_DATO = '#eceff2';
const COLOR_BORDE = '#ffffff';
const SVG_NS = 'http://www.w3.org/2000/svg';

const OPCIONES_POR_DEFECTO = {
  proyeccion: 'mercator',      // 'mercator' | 'equirectangular'
  padding: 12,
  paleta: 'teal',
  escala: 'cuantil',           // 'cuantil' | 'intervalo' | 'cortes'
  pasos: 5,
  cortes: null,                // array de números si escala === 'cortes'
  leyenda: true,
  tituloLeyenda: '',
  etiquetas: 'auto',           // 'auto' (aparecen al acercar, sin encimarse) | true | false
  tamanoEtiqueta: 10,          // px en pantalla; NO crece con el zoom
  anchoMinimoEtiqueta: 46,     // un polígono más angosto que esto no recibe etiqueta
  maxEtiquetas: 60,            // tope de etiquetas simultáneas
  zoom: true,
  zoomMax: 24,
  seleccionMultiple: false,
  formatoValor: (v) => new Intl.NumberFormat('es-PE').format(v),
  textoSinDato: 'Sin dato',
  tooltip: null,               // (feature, valor, fila) => string HTML
  onClick: null,               // (id, feature, fila) => void
  onSeleccion: null,           // (ids) => void
  altoMinimo: 320,
};

/** Normaliza códigos: string, sin espacios, mayúsculas. Preserva ceros a la izquierda. */
function normalizarId(v) {
  if (v === null || v === undefined) return '';
  return String(v).trim().toUpperCase();
}

/* ─────────────────────────── proyecciones ─────────────────────────── */

const PROYECCIONES = {
  mercator(lon, lat) {
    const rad = Math.PI / 180;
    const y = Math.max(-85.05, Math.min(85.05, lat)) * rad;
    return [lon * rad, Math.log(Math.tan(Math.PI / 4 + y / 2))];
  },
  equirectangular(lon, lat) {
    return [lon, lat];
  },
};

/* ─────────────────────────── escalas de color ─────────────────────────── */

function cortesCuantil(valores, pasos) {
  const orden = valores.slice().sort((a, b) => a - b);
  const cortes = [];
  for (let i = 1; i < pasos; i++) {
    const pos = (orden.length - 1) * (i / pasos);
    const bajo = Math.floor(pos);
    const alto = Math.ceil(pos);
    cortes.push(orden[bajo] + (orden[alto] - orden[bajo]) * (pos - bajo));
  }
  return cortes;
}

function cortesIntervalo(valores, pasos) {
  const min = Math.min(...valores);
  const max = Math.max(...valores);
  const paso = (max - min) / pasos;
  const cortes = [];
  for (let i = 1; i < pasos; i++) cortes.push(min + paso * i);
  return cortes;
}

/** Interpola una paleta de N colores a `pasos` colores. */
function rampa(colores, pasos) {
  if (pasos <= 1) return [colores[colores.length - 1]];
  const hex = (c) => [1, 3, 5].map((i) => parseInt(c.substr(i, 2), 16));
  const salida = [];
  for (let i = 0; i < pasos; i++) {
    const t = (i / (pasos - 1)) * (colores.length - 1);
    const a = hex(colores[Math.floor(t)]);
    const b = hex(colores[Math.min(colores.length - 1, Math.ceil(t))]);
    const f = t - Math.floor(t);
    const mix = a.map((v, k) => Math.round(v + (b[k] - v) * f));
    salida.push('#' + mix.map((v) => v.toString(16).padStart(2, '0')).join(''));
  }
  return salida;
}

/* ─────────────────────────── clase principal ─────────────────────────── */

export class PeruMap {
  constructor(contenedor, opciones = {}) {
    this.el = typeof contenedor === 'string' ? document.querySelector(contenedor) : contenedor;
    if (!this.el) throw new Error('PeruMap: contenedor no encontrado');

    this.opts = { ...OPCIONES_POR_DEFECTO, ...opciones };
    this.features = [];
    this.datos = new Map();      // id -> { valor, fila }
    this.seleccion = new Set();
    this.transform = { k: 1, x: 0, y: 0 };

    this.#construirDOM();
    this.#enlazarEventos();
  }

  /* ------------------------------- API pública ------------------------------- */

  /**
   * Carga (o reemplaza) la capa geográfica.
   * @param {object|string} geojson FeatureCollection o URL a un .json
   * @param {{campoId:string|function, campoNombre:string|function}} conf
   */
  async cargarGeografia(geojson, conf = {}) {
    const gj = typeof geojson === 'string' ? await (await fetch(geojson)).json() : geojson;
    const campoId = conf.campoId ?? 'id';
    const campoNombre = conf.campoNombre ?? 'nombre';

    const leer = (campo) => (f) =>
      typeof campo === 'function' ? campo(f) : (f.properties?.[campo] ?? f[campo]);

    const leerId = leer(campoId);
    const leerNombre = leer(campoNombre);

    this.features = (gj.features ?? []).map((f, i) => ({
      id: normalizarId(leerId(f) ?? i),
      nombre: leerNombre(f) ?? '',
      geometria: f.geometry,
      props: f.properties ?? {},
      anillos: null,
      centroide: null,
    }));

    this.#proyectar();
    this.transform = { k: 1, x: 0, y: 0 };
    this.#render();
    return this;
  }

  /**
   * Capa de bordes dibujada encima del coroplético, sin relleno ni eventos.
   * Sirve para marcar los límites de región sobre un mapa de UGEL.
   * @param {object|string|null} geojson FeatureCollection, URL, o null para quitarla
   */
  async setContorno(geojson) {
    if (!geojson) { this.contorno = []; this.#renderContorno(); return this; }
    const gj = typeof geojson === 'string' ? await (await fetch(geojson)).json() : geojson;
    this.contorno = (gj.features ?? []).map((f) => ({ geometria: f.geometry }));
    this.#renderContorno();
    return this;
  }

  /**
   * Une los datos por código y repinta.
   * @param {Array<object>|Map} filas
   * @param {{campoId?:string, campoValor?:string}} conf
   */
  setDatos(filas, conf = {}) {
    const campoId = conf.campoId ?? 'id';
    const campoValor = conf.campoValor ?? 'valor';

    this.datos = new Map();
    const iterable = filas instanceof Map ? filas.entries() : filas.map((f) => [f[campoId], f]);
    for (const [id, fila] of iterable) {
      const valor = typeof fila === 'number' ? fila : Number(fila[campoValor]);
      if (!Number.isFinite(valor)) continue;
      this.datos.set(normalizarId(id), { valor, fila: typeof fila === 'number' ? { valor } : fila });
    }
    this.#calcularEscala();
    this.#pintar();
    this.#renderLeyenda();
    return this;
  }

  /** Cambia opciones en caliente (paleta, escala, formato, etc.) y repinta. */
  setOpciones(parciales) {
    Object.assign(this.opts, parciales);
    this.#colocarEtiquetas();
    this.#calcularEscala();
    this.#pintar();
    this.#renderLeyenda();
    return this;
  }

  seleccionar(id, { emitir = true } = {}) {
    const clave = normalizarId(id);
    if (!this.opts.seleccionMultiple) this.seleccion.clear();
    if (this.seleccion.has(clave)) this.seleccion.delete(clave);
    else this.seleccion.add(clave);
    this.#pintar();
    if (emitir) this.opts.onSeleccion?.([...this.seleccion]);
    return this;
  }

  limpiarSeleccion() {
    this.seleccion.clear();
    this.#pintar();
    this.opts.onSeleccion?.([]);
    return this;
  }

  /** Acerca la vista a un polígono por código. */
  zoomA(id, margen = 0.15) {
    const f = this.features.find((x) => x.id === normalizarId(id));
    if (!f) return this;
    const [x0, y0, x1, y1] = f.bbox;
    const w = this.ancho, h = this.alto;
    const k = Math.min(this.opts.zoomMax, (1 - margen) * Math.min(w / (x1 - x0), h / (y1 - y0)));
    this.transform = {
      k,
      x: w / 2 - k * (x0 + x1) / 2,
      y: h / 2 - k * (y0 + y1) / 2,
    };
    this.#aplicarTransform(true);
    return this;
  }

  resetZoom() {
    this.transform = { k: 1, x: 0, y: 0 };
    this.#aplicarTransform(true);
    return this;
  }

  /** Devuelve el SVG como string (para exportar o incrustar en un PDF). */
  exportarSVG() {
    return new XMLSerializer().serializeToString(this.svg);
  }

  destruir() {
    this.ro?.disconnect();
    this.el.innerHTML = '';
  }

  /* ------------------------------- internos ------------------------------- */

  #construirDOM() {
    this.el.classList.add('pm-root');
    this.el.innerHTML = '';

    this.svg = document.createElementNS(SVG_NS, 'svg');
    this.svg.setAttribute('class', 'pm-svg');
    this.svg.setAttribute('xmlns', SVG_NS);
    this.capa = document.createElementNS(SVG_NS, 'g');
    this.capaContorno = document.createElementNS(SVG_NS, 'g');
    this.capaContorno.setAttribute('class', 'pm-contorno');
    this.capaEtiquetas = document.createElementNS(SVG_NS, 'g');
    this.capaEtiquetas.setAttribute('class', 'pm-etiquetas');
    this.svg.append(this.capa, this.capaContorno, this.capaEtiquetas);
    this.contorno = [];

    this.tooltip = document.createElement('div');
    this.tooltip.className = 'pm-tooltip';
    this.tooltip.hidden = true;

    this.leyenda = document.createElement('div');
    this.leyenda.className = 'pm-leyenda';

    this.el.append(this.svg, this.tooltip, this.leyenda);
  }

  #enlazarEventos() {
    this.ro = new ResizeObserver(() => this.#render());
    this.ro.observe(this.el);

    this.svg.addEventListener('mousemove', (e) => {
      const path = e.target.closest('path[data-id]');
      if (!path) return this.#ocultarTooltip();
      this.#mostrarTooltip(path.dataset.id, e);
    });
    this.svg.addEventListener('mouseleave', () => this.#ocultarTooltip());

    this.svg.addEventListener('click', (e) => {
      const path = e.target.closest('path[data-id]');
      if (!path) return;
      const f = this.features.find((x) => x.id === path.dataset.id);
      this.seleccionar(path.dataset.id);
      this.opts.onClick?.(path.dataset.id, f, this.datos.get(path.dataset.id)?.fila ?? null);
    });

    if (this.opts.zoom) this.#habilitarZoom();
  }

  #habilitarZoom() {
    let arrastrando = false, ultimo = null;

    this.svg.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = this.svg.getBoundingClientRect();
      const px = e.clientX - rect.left, py = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2;
      const k = Math.max(1, Math.min(this.opts.zoomMax, this.transform.k * factor));
      const real = k / this.transform.k;
      this.transform = {
        k,
        x: px - (px - this.transform.x) * real,
        y: py - (py - this.transform.y) * real,
      };
      this.#aplicarTransform();
    }, { passive: false });

    this.svg.addEventListener('pointerdown', (e) => {
      arrastrando = true; ultimo = [e.clientX, e.clientY];
      this.svg.setPointerCapture(e.pointerId);
      this.svg.classList.add('pm-arrastrando');
    });
    this.svg.addEventListener('pointermove', (e) => {
      if (!arrastrando) return;
      this.transform.x += e.clientX - ultimo[0];
      this.transform.y += e.clientY - ultimo[1];
      ultimo = [e.clientX, e.clientY];
      this.#aplicarTransform();
    });
    const soltar = (e) => {
      arrastrando = false;
      this.svg.classList.remove('pm-arrastrando');
      if (e.pointerId != null && this.svg.hasPointerCapture?.(e.pointerId)) {
        this.svg.releasePointerCapture(e.pointerId);
      }
    };
    this.svg.addEventListener('pointerup', soltar);
    this.svg.addEventListener('pointercancel', soltar);
  }

  #aplicarTransform(animado = false) {
    const t = `translate(${this.transform.x},${this.transform.y}) scale(${this.transform.k})`;
    this.capa.style.transition = animado ? 'transform .45s cubic-bezier(.4,0,.2,1)' : 'none';
    this.capaEtiquetas.style.transition = this.capa.style.transition;
    this.capa.setAttribute('transform', t);
    this.capaContorno.style.transition = this.capa.style.transition;
    this.capaContorno.setAttribute('transform', t);
    // Las etiquetas NO se escalan: se recolocan para que el texto no crezca con el zoom.
    if (animado) setTimeout(() => this.#colocarEtiquetas(), 460);
    else {
      cancelAnimationFrame(this._rafEtiquetas);
      this._rafEtiquetas = requestAnimationFrame(() => this.#colocarEtiquetas());
    }
  }

  /** Proyecta lon/lat a coordenadas de pantalla ajustadas al contenedor. */
  #proyectar() {
    const rect = this.el.getBoundingClientRect();
    this.ancho = Math.max(200, rect.width || 600);
    this.alto = Math.max(this.opts.altoMinimo, rect.height || this.ancho * 1.15);

    const proy = PROYECCIONES[this.opts.proyeccion] ?? PROYECCIONES.mercator;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

    for (const f of this.features) {
      f.anillosCrudos = anillosDeGeometria(f.geometria).map((anillo) =>
        anillo.map(([lon, lat]) => {
          const [x, y] = proy(lon, lat);
          if (x < minX) minX = x; if (x > maxX) maxX = x;
          if (y < minY) minY = y; if (y > maxY) maxY = y;
          return [x, y];
        })
      );
    }

    const p = this.opts.padding;
    const escala = Math.min((this.ancho - p * 2) / (maxX - minX), (this.alto - p * 2) / (maxY - minY));
    const dx = (this.ancho - (maxX - minX) * escala) / 2 - minX * escala;
    const dy = (this.alto - (maxY - minY) * escala) / 2 + maxY * escala;

    // Se guardan para proyectar la capa de contorno con EL MISMO encuadre.
    this.proy = { fn: proy, escala, dx, dy };

    for (const f of this.features) {
      let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
      let sx = 0, sy = 0, n = 0;
      f.d = f.anillosCrudos.map((anillo) => {
        let d = '';
        for (let i = 0; i < anillo.length; i++) {
          const x = anillo[i][0] * escala + dx;
          const y = -anillo[i][1] * escala + dy;
          d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
          if (x < bx0) bx0 = x; if (x > bx1) bx1 = x;
          if (y < by0) by0 = y; if (y > by1) by1 = y;
          sx += x; sy += y; n++;
        }
        return d + 'Z';
      }).join('');
      f.bbox = [bx0, by0, bx1, by1];
      f.centroide = [sx / n, sy / n];
      delete f.anillosCrudos;
    }
  }

  #render() {
    if (!this.features.length) return;
    this.#proyectar();
    this.svg.setAttribute('viewBox', `0 0 ${this.ancho} ${this.alto}`);
    this.svg.setAttribute('height', this.alto);

    this.capa.innerHTML = '';
    this.capaEtiquetas.innerHTML = '';

    for (const f of this.features) {
      const path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', f.d);
      path.setAttribute('data-id', f.id);
      path.setAttribute('stroke', COLOR_BORDE);
      path.setAttribute('vector-effect', 'non-scaling-stroke');
      path.setAttribute('class', 'pm-area');
      this.capa.appendChild(path);

      const txt = document.createElementNS(SVG_NS, 'text');
      txt.setAttribute('text-anchor', 'middle');
      txt.setAttribute('font-size', this.opts.tamanoEtiqueta);
      txt.textContent = f.nombre;
      f.txt = txt;
      f.area = (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]);
      this.capaEtiquetas.appendChild(txt);
    }

    this.#renderContorno();
    this.#colocarEtiquetas();
    this.#calcularEscala();
    this.#pintar();
    this.#renderLeyenda();
    this.#aplicarTransform();
  }

  /**
   * Coloca las etiquetas en coordenadas de pantalla, con tamaño fijo.
   * Descarta las que caen sobre un polígono demasiado chico y las que se encimarían.
   */
  #colocarEtiquetas() {
    if (this.opts.etiquetas === false) {
      for (const f of this.features) if (f.txt) f.txt.style.display = 'none';
      return;
    }
    const { k, x: tx, y: ty } = this.transform;
    const tam = this.opts.tamanoEtiqueta;
    const auto = this.opts.etiquetas === 'auto';
    const anchoMin = auto ? this.opts.anchoMinimoEtiqueta : 0;

    // Los polígonos grandes se etiquetan primero: si algo se descarta, que sea lo chico.
    const orden = this.features.filter((f) => f.txt).sort((a, b) => b.area - a.area);
    const puestas = [];

    for (const f of orden) {
      const t = f.txt;
      const anchoEnPantalla = (f.bbox[2] - f.bbox[0]) * k;
      const cx = f.centroide[0] * k + tx;
      const cy = f.centroide[1] * k + ty;

      const fuera = cx < -40 || cy < -20 || cx > this.ancho + 40 || cy > this.alto + 20;
      if (fuera || anchoEnPantalla < anchoMin || puestas.length >= this.opts.maxEtiquetas) {
        t.style.display = 'none';
        continue;
      }

      t.setAttribute('x', cx.toFixed(1));
      t.setAttribute('y', cy.toFixed(1));
      t.style.display = '';

      let ancho;
      try { ancho = t.getComputedTextLength(); } catch { ancho = 0; }
      if (!ancho) ancho = t.textContent.length * tam * 0.52;
      const caja = [cx - ancho / 2 - 2, cy - tam, cx + ancho / 2 + 2, cy + 3];

      const choca = puestas.some((c) =>
        caja[0] < c[2] && caja[2] > c[0] && caja[1] < c[3] && caja[3] > c[1]);

      if (choca && auto) t.style.display = 'none';
      else puestas.push(caja);
    }
  }

  #renderContorno() {
    this.capaContorno.innerHTML = '';
    if (!this.contorno?.length || !this.proy) return;
    const { fn, escala, dx, dy } = this.proy;

    for (const c of this.contorno) {
      let d = '';
      for (const anillo of anillosDeGeometria(c.geometria)) {
        for (let i = 0; i < anillo.length; i++) {
          const [px, py] = fn(anillo[i][0], anillo[i][1]);
          d += (i === 0 ? 'M' : 'L') + (px * escala + dx).toFixed(1) + ',' + (-py * escala + dy).toFixed(1);
        }
        d += 'Z';
      }
      const path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', d);
      path.setAttribute('vector-effect', 'non-scaling-stroke');
      this.capaContorno.appendChild(path);
    }
  }

  #calcularEscala() {
    const valores = [...this.datos.values()].map((d) => d.valor);
    const pasos = this.opts.escala === 'cortes' && this.opts.cortes
      ? this.opts.cortes.length + 1
      : this.opts.pasos;

    this.colores = rampa(PALETAS[this.opts.paleta] ?? this.opts.paleta, pasos);

    if (!valores.length) { this.cortes = []; return; }
    if (this.opts.escala === 'cortes' && this.opts.cortes) this.cortes = this.opts.cortes.slice();
    else if (this.opts.escala === 'intervalo') this.cortes = cortesIntervalo(valores, pasos);
    else this.cortes = cortesCuantil(valores, pasos);
  }

  #color(valor) {
    if (valor === undefined) return COLOR_SIN_DATO;
    let i = 0;
    while (i < this.cortes.length && valor > this.cortes[i]) i++;
    return this.colores[i] ?? this.colores[this.colores.length - 1];
  }

  #pintar() {
    for (const path of this.capa.children) {
      const id = path.dataset.id;
      const d = this.datos.get(id);
      path.setAttribute('fill', this.#color(d?.valor));
      path.classList.toggle('pm-seleccionado', this.seleccion.has(id));
      path.classList.toggle('pm-atenuado', this.seleccion.size > 0 && !this.seleccion.has(id));
    }
  }

  #renderLeyenda() {
    if (!this.opts.leyenda || !this.colores) { this.leyenda.innerHTML = ''; return; }
    const fmt = this.opts.formatoValor;
    const items = this.colores.map((c, i) => {
      const desde = i === 0 ? null : this.cortes[i - 1];
      const hasta = i === this.colores.length - 1 ? null : this.cortes[i];
      const etiqueta = desde === null
        ? `< ${fmt(Math.round(hasta ?? 0))}`
        : hasta === null
          ? `≥ ${fmt(Math.round(desde))}`
          : `${fmt(Math.round(desde))} – ${fmt(Math.round(hasta))}`;
      return `<span class="pm-leyenda-item"><i style="background:${c}"></i>${etiqueta}</span>`;
    }).join('');

    this.leyenda.innerHTML =
      (this.opts.tituloLeyenda ? `<span class="pm-leyenda-titulo">${this.opts.tituloLeyenda}</span>` : '') +
      items +
      `<span class="pm-leyenda-item"><i style="background:${COLOR_SIN_DATO}"></i>${this.opts.textoSinDato}</span>`;
  }

  #mostrarTooltip(id, evt) {
    const f = this.features.find((x) => x.id === id);
    const d = this.datos.get(id);
    if (!f) return;

    this.tooltip.innerHTML = this.opts.tooltip
      ? this.opts.tooltip(f, d?.valor, d?.fila ?? null)
      : `<strong>${f.nombre || id}</strong><span>${d ? this.opts.formatoValor(d.valor) : this.opts.textoSinDato}</span>`;

    const rect = this.el.getBoundingClientRect();
    const x = evt.clientX - rect.left;
    const y = evt.clientY - rect.top;
    this.tooltip.hidden = false;
    this.tooltip.style.left = Math.min(x + 14, rect.width - this.tooltip.offsetWidth - 8) + 'px';
    this.tooltip.style.top = Math.max(8, y - this.tooltip.offsetHeight - 10) + 'px';
  }

  #ocultarTooltip() { this.tooltip.hidden = true; }
}

/** Extrae los anillos exteriores e interiores de cualquier geometría GeoJSON. */
function anillosDeGeometria(geom) {
  if (!geom) return [];
  switch (geom.type) {
    case 'Polygon': return geom.coordinates;
    case 'MultiPolygon': return geom.coordinates.flat();
    case 'GeometryCollection': return geom.geometries.flatMap(anillosDeGeometria);
    default: return [];
  }
}

export default PeruMap;

/**
 * Panel privado de rendimiento — Google Apps Script.
 *
 * Lee GA4 con la Data API y arma una página con los números que importan:
 * cuánta gente sale de la cartelera hacia una boletería, por qué película, por
 * qué cine y con cuánta anticipación.
 *
 * Por qué vive acá y no adentro de sitedigo.com: la web es estática (GitHub
 * Pages), no tiene backend donde guardar una credencial, así que no puede
 * consultar GA4 sin exponer el acceso a la propiedad. Este web app corre con tu
 * cuenta de Google y se despliega con acceso "Sólo yo": la propia sesión de
 * Google es la puerta. Podés linkearlo desde donde quieras — a quien no sea vos
 * le va a pedir login y le va a dar 401.
 *
 * ──────────────────────────────────────────────────────────────────────
 * SETUP:
 *   1. script.google.com → Nuevo proyecto → pegá este archivo
 *   2. Servicios (+) → agregá "Google Analytics Data API" → id: AnalyticsData
 *   3. Completá PROPERTY_ID abajo (el mismo de ga4_setup.gs)
 *   4. Implementar → Nueva implementación → Aplicación web
 *        - Ejecutar como: Yo
 *        - Quién tiene acceso: SÓLO YO      ← importante
 *      Copiá la URL: ese es tu panel.
 *
 * Antes de que esto muestre algo hay que correr ga4_setup.gs, y esperar a que
 * entren datos: las dimensiones sólo aplican a los eventos que llegan después
 * de darlas de alta.
 * ──────────────────────────────────────────────────────────────────────
 */

const PROPERTY_ID = "";   // ⚠️ el mismo número que en ga4_setup.gs
const DIAS = 28;

function doGet() {
  return HtmlService.createHtmlOutput(construirPanel())
    .setTitle("Rendimiento · Si te digo")
    .addMetaTag("viewport", "width=device-width, initial-scale=1");
}

// ── Acceso a GA4 ───────────────────────────────────────────────────────

function _reporte(opts) {
  const req = {
    dateRanges: [{ startDate: (opts.dias || DIAS) + "daysAgo", endDate: "today" }],
    dimensions: (opts.dims || []).map(function (d) { return { name: d }; }),
    metrics: (opts.metrics || ["eventCount"]).map(function (m) { return { name: m }; }),
    limit: opts.limite || 20,
  };
  if (opts.evento) {
    req.dimensionFilter = {
      filter: { fieldName: "eventName", stringFilter: { value: opts.evento } },
    };
  }
  if (opts.orden) {
    req.orderBys = [{ metric: { metricName: opts.orden }, desc: true }];
  }
  try {
    const res = AnalyticsData.Properties.runReport(req, "properties/" + PROPERTY_ID);
    return (res.rows || []).map(function (r) {
      return {
        claves: (r.dimensionValues || []).map(function (v) { return v.value; }),
        valores: (r.metricValues || []).map(function (v) { return Number(v.value || 0); }),
      };
    });
  } catch (e) {
    // Lo más común: la dimensión todavía no está dada de alta (ga4_setup.gs)
    // o no entraron datos desde que se creó.
    return { error: String(e.message || e) };
  }
}

function _total(opts) {
  const r = _reporte(opts);
  if (r.error) return r;
  return r.reduce(function (a, x) { return a + x.valores[0]; }, 0);
}

// ── Armado del panel ───────────────────────────────────────────────────

function construirPanel() {
  if (!PROPERTY_ID) {
    return _pagina("<p>Falta completar <code>PROPERTY_ID</code> en el script.</p>");
  }

  const clicks = _total({ evento: "click_entradas", dias: DIAS });
  const guardados = _total({ evento: "agendar_funcion", dias: DIAS });
  const sesiones = _total({ metrics: ["sessions"], dias: DIAS });

  const bloques = [];

  // 1. El número que importa. La comparación sale de restarle al total de 56
  // días el de los últimos 28: la Data API no acepta rangos que no terminen
  // hoy sin complicar la request.
  let variacion = "";
  const dobleVentana = _total({ evento: "click_entradas", dias: DIAS * 2 });
  if (typeof clicks === "number" && typeof dobleVentana === "number") {
    const anterior = dobleVentana - clicks;
    if (anterior > 0) {
      const pct = Math.round((clicks - anterior) / anterior * 100);
      variacion = (pct >= 0 ? "+" : "") + pct + "% vs. los " + DIAS + " días previos";
    }
  }
  bloques.push(_tarjetas([
    ["Clicks a boletería", clicks, variacion],
    ["Funciones agendadas", guardados, "el botón +"],
    ["Sesiones", sesiones, ""],
    ["Sesiones que terminan en click",
      (typeof clicks === "number" && typeof sesiones === "number" && sesiones)
        ? Math.round(clicks / sesiones * 100) + "%" : "—",
      "la tasa que le importa a un cine"],
  ]));

  // 2. Qué mueve gente
  bloques.push(_barras("Películas que más mandan gente a la boletería",
    _reporte({ evento: "click_entradas", dims: ["customEvent:pelicula"],
               orden: "eventCount", limite: 12 })));
  bloques.push(_barras("Cines",
    _reporte({ evento: "click_entradas", dims: ["customEvent:cine"],
               orden: "eventCount", limite: 12 })));
  bloques.push(_barras("Ciclos y festivales",
    _reporte({ evento: "click_entradas", dims: ["customEvent:ciclo"],
               orden: "eventCount", limite: 8 })));

  // 3. Cuándo deciden — define cuándo conviene publicar
  const antic = _reporte({ evento: "click_entradas",
                           dims: ["customEvent:dias_anticipacion"], limite: 100 });
  bloques.push(_barras("Con cuánta anticipación compran", _agrupar(antic, function (k) {
    const n = parseInt(k, 10);
    if (isNaN(n)) return "sin dato";
    if (n <= 0) return "mismo día";
    if (n <= 2) return "1-2 días";
    if (n <= 7) return "3-7 días";
    if (n <= 14) return "1-2 semanas";
    return "más de 2 semanas";
  }, ["mismo día", "1-2 días", "3-7 días", "1-2 semanas", "más de 2 semanas", "sin dato"])));

  // 4. De dónde viene la gente que efectivamente clickea
  bloques.push(_barras("Canal de origen de los clicks",
    _reporte({ evento: "click_entradas", dims: ["customEvent:canal"],
               orden: "eventCount", limite: 10 })));

  // 5. Qué busca la gente — y qué no encuentra
  bloques.push(_barras("Búsquedas más frecuentes",
    _reporte({ evento: "buscar", dims: ["customEvent:termino"],
               orden: "eventCount", limite: 12 })));

  // 6. Dónde clickean dentro de la grilla
  bloques.push(_barras("Posición en la lista al hacer click",
    _agrupar(_reporte({ evento: "click_entradas", dims: ["customEvent:posicion"], limite: 100 }),
      function (k) {
        const n = parseInt(k, 10);
        if (isNaN(n)) return "sin dato";
        if (n <= 3) return "1-3 (arriba de todo)";
        if (n <= 10) return "4-10";
        if (n <= 25) return "11-25";
        return "más abajo de 25";
      }, ["1-3 (arriba de todo)", "4-10", "11-25", "más abajo de 25", "sin dato"])));

  return _pagina(bloques.join("\n"));
}

// ── Helpers de presentación ────────────────────────────────────────────

function _agrupar(filas, fn, orden) {
  if (filas.error) return filas;
  const acc = {};
  filas.forEach(function (f) {
    const k = fn(f.claves[0]);
    acc[k] = (acc[k] || 0) + f.valores[0];
  });
  return (orden || Object.keys(acc))
    .filter(function (k) { return acc[k]; })
    .map(function (k) { return { claves: [k], valores: [acc[k]] }; });
}

function _esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function _tarjetas(items) {
  const cel = items.map(function (it) {
    const val = (it[1] && it[1].error) ? "—" : it[1];
    return '<div style="flex:1;min-width:150px;background:#111;border:1px solid #262626;'
      + 'border-radius:10px;padding:14px 16px">'
      + '<div style="font-size:12px;color:#777;text-transform:uppercase;letter-spacing:.06em">'
      + _esc(it[0]) + '</div>'
      + '<div style="font-size:30px;font-weight:600;margin:4px 0 2px">' + _esc(val) + '</div>'
      + '<div style="font-size:12px;color:#666">' + _esc(it[2] || "") + '</div>'
      + '</div>';
  }).join("");
  return '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:26px">' + cel + '</div>';
}

function _barras(titulo, filas) {
  let cuerpo;
  if (filas && filas.error) {
    cuerpo = '<p style="color:#b06000;font-size:13px;margin:0">Sin datos todavía. '
           + 'Si recién corriste <code>ga4_setup.gs</code>, GA4 empieza a mostrar el '
           + 'parámetro con los eventos que entran a partir de ahí.<br>'
           + '<span style="color:#555">' + _esc(filas.error) + '</span></p>';
  } else if (!filas || !filas.length) {
    cuerpo = '<p style="color:#666;font-size:13px;margin:0">Sin datos en el período.</p>';
  } else {
    const max = Math.max.apply(null, filas.map(function (f) { return f.valores[0]; })) || 1;
    cuerpo = filas.map(function (f) {
      const pct = Math.round(f.valores[0] / max * 100);
      return '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
        + '<div style="width:210px;font-size:13px;color:#ccc;overflow:hidden;'
        + 'text-overflow:ellipsis;white-space:nowrap">' + _esc(f.claves[0] || "(vacío)") + '</div>'
        + '<div style="flex:1;background:#1a1a1a;border-radius:3px;height:16px">'
        + '<div style="width:' + pct + '%;background:#00d060;height:16px;border-radius:3px"></div></div>'
        + '<div style="width:52px;text-align:right;font-size:13px;color:#888">'
        + f.valores[0] + '</div></div>';
    }).join("");
  }
  return '<section style="margin-bottom:30px">'
    + '<h2 style="font-size:15px;margin:0 0 12px;color:#e0e0e0;font-weight:600">'
    + _esc(titulo) + '</h2>' + cuerpo + '</section>';
}

function _pagina(contenido) {
  const hoy = Utilities.formatDate(new Date(), "GMT-3", "d 'de' MMMM, HH:mm");
  return '<!doctype html><html lang="es"><head><meta charset="utf-8">'
    + '<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
    + '<body style="margin:0;background:#0a0a0a;color:#e0e0e0;'
    + "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif\">"
    + '<div style="max-width:860px;margin:0 auto;padding:26px 18px 60px">'
    + '<h1 style="font-size:20px;margin:0 0 2px">Rendimiento de la cartelera</h1>'
    + '<p style="color:#666;font-size:13px;margin:0 0 24px">Últimos ' + DIAS
    + ' días · actualizado ' + _esc(hoy) + '</p>'
    + contenido
    + '<p style="color:#444;font-size:12px;border-top:1px solid #1a1a1a;padding-top:14px">'
    + 'Panel privado. Los datos salen de GA4 vía Data API.</p>'
    + '</div></body></html>';
}

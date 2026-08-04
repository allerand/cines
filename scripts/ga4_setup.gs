/**
 * Alta de las dimensiones personalizadas de GA4 — Google Apps Script.
 *
 * GA4 recibe los parámetros que manda index.html igual, pero no los muestra en
 * ningún informe hasta que están dados de alta como "dimensión personalizada".
 * Eso normalmente se hace a mano, un formulario por parámetro. Esto lo hace por
 * API en una corrida, y es idempotente: si ya existen, no las duplica.
 *
 * Corre con tu cuenta de Google, que ya es administradora de la propiedad, así
 * que no hay service account ni JSON de credenciales dando vueltas.
 *
 * ──────────────────────────────────────────────────────────────────────
 * SETUP:
 *   1. script.google.com → Nuevo proyecto → pegá este archivo
 *   2. Servicios (el "+" al lado de Services) → agregá
 *        "Google Analytics Admin API"   → identificador: AnalyticsAdmin
 *   3. Poné abajo el PROPERTY_ID (número, NO el G-XXXXXXX):
 *        GA4 → Admin → Configuración de la propiedad → ID de la propiedad
 *   4. Ejecutar → setupDimensiones. Mirá el log.
 * ──────────────────────────────────────────────────────────────────────
 */

const PROPERTY_ID = "";   // ⚠️ completar, p.ej. "123456789"

// Los mismos nombres que manda index.html en paramsFuncion(). Si algún día se
// agrega un parámetro nuevo allá, se agrega acá y se vuelve a correr.
const DIMENSIONES = [
  ["cine",              "Cine",                 "Sala donde se da la función"],
  ["pelicula",          "Película",             "Título en español de la película"],
  ["ciclo",             "Ciclo",                "Ciclo o festival al que pertenece"],
  ["fecha_funcion",     "Fecha de la función",  "Fecha de la función (YYYY-MM-DD)"],
  ["dias_anticipacion", "Días de anticipación", "Días entre el click y la función"],
  ["canal",             "Canal de origen",      "De dónde llegó la visita (utm_medium, referido o directo)"],
  ["vista",             "Vista",                "Si la función se vio desde el día o desde el buscador"],
  ["posicion",          "Posición en la lista", "Puesto de la función en la grilla al momento del click"],
  // Del evento `buscar` (y `compartir_busqueda`).
  ["termino",           "Término buscado",      "Lo que la persona escribió en el buscador"],
  ["resultados",        "Resultados",           "Cuántas funciones devolvió esa búsqueda (0 = no encontró nada)"],
];

function setupDimensiones() {
  if (!PROPERTY_ID) {
    Logger.log("Falta completar PROPERTY_ID arriba.");
    return;
  }
  const parent = "properties/" + PROPERTY_ID;

  // GA4 permite hasta 50 dimensiones de evento; listamos primero para no
  // gastar cupo re-creando las que ya están.
  const existentes = {};
  let pageToken = null;
  do {
    const res = AnalyticsAdmin.Properties.CustomDimensions.list(
      parent, { pageSize: 200, pageToken: pageToken });
    (res.customDimensions || []).forEach(function (d) {
      existentes[d.parameterName] = true;
    });
    pageToken = res.nextPageToken;
  } while (pageToken);

  let creadas = 0, ya = 0, fallidas = 0;
  DIMENSIONES.forEach(function (d) {
    const param = d[0], nombre = d[1], desc = d[2];
    if (existentes[param]) {
      Logger.log("· ya existía: " + param);
      ya++;
      return;
    }
    try {
      AnalyticsAdmin.Properties.CustomDimensions.create({
        parameterName: param,
        displayName: nombre,
        description: desc,
        scope: "EVENT",
      }, parent);
      Logger.log("✓ creada: " + param);
      creadas++;
    } catch (e) {
      Logger.log("✗ " + param + " — " + e.message);
      fallidas++;
    }
  });

  Logger.log("Listo: " + creadas + " creadas, " + ya + " ya estaban, " + fallidas + " fallaron.");
  Logger.log("Las dimensiones sólo aplican a los datos que ENTRAN a partir de "
           + "ahora: los eventos de antes quedan sin el parámetro visible.");
}

/** Para chequear qué hay dado de alta hoy. */
function listarDimensiones() {
  const res = AnalyticsAdmin.Properties.CustomDimensions.list("properties/" + PROPERTY_ID, { pageSize: 200 });
  (res.customDimensions || []).forEach(function (d) {
    Logger.log(d.scope + "  " + d.parameterName + "  → " + d.displayName);
  });
}

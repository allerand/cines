/**
 * Newsletter cines — Google Apps Script.
 *
 * Hace dos cosas:
 *   1) Endpoint POST público (doPost) que recibe {email} del form de sitedigo
 *      y lo agrega a la primera hoja del Spreadsheet activo.
 *   2) Función sendNewsletter() que se dispara con un time-trigger todos los
 *      jueves a las 9 AM (configurás abajo). Lee la cartelera de GitHub,
 *      arma el HTML día por día y manda un mail a cada suscriptor.
 *
 * ──────────────────────────────────────────────────────────────────────
 * SETUP (one-time):
 *   1. Crear un Google Sheet nuevo. La primera hoja debe tener en A1:
 *        email
 *      (después se llena con cada suscripción)
 *   2. Extensions → Apps Script → pegar TODO este archivo
 *   3. Configurar abajo CARTELERA_URL y FROM_NAME
 *   4. Deploy → New deployment:
 *        - Type: Web app
 *        - Execute as: Me
 *        - Who has access: Anyone
 *      Copiar el "Web app URL" → pegarlo en index.html como APPS_SCRIPT_URL
 *   5. Triggers (reloj a la izquierda) → Add trigger:
 *        - Function: sendNewsletter
 *        - Source: Time-driven → Week timer → Thursday → 9 AM-10 AM
 *
 * Eso es todo. El form de sitedigo va a appendear a la sheet, y todos los
 * jueves a las 9 AM-10 AM Apps Script va a mandar el newsletter automático.
 * ──────────────────────────────────────────────────────────────────────
 */

// ⚙️ Config — cambiá esto antes de deployar
const CARTELERA_URL = "https://raw.githubusercontent.com/allerand/cines/main/data/cartelera.json";
const LOGO_URL = "https://raw.githubusercontent.com/allerand/cines/main/logo.png";
const SITE_URL = "https://sitedigo.com";
const BRAND_NAME = "Si te digo producciones";
const FROM_NAME = "Si te digo producciones";
const SUBJECT_PREFIX = "Cartelera de cine — semana";

// Paleta — igual a la web (index.html)
const T_BG       = "#0a0a0a";
const T_BG2      = "#111";
const T_BG3      = "#1a1a1a";
const T_BORDER   = "#2a2a2a";
const T_TEXT     = "#e0e0e0";
const T_MUTED    = "#666";
const T_ACCENT   = "#00d060";
const T_FONT     = "-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif";

// Localización
const DAYS_ES = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"];
const MONTHS_ES = ["enero","febrero","marzo","abril","mayo","junio",
                   "julio","agosto","septiembre","octubre","noviembre","diciembre"];


// ───── 1. Endpoint del form ────────────────────────────────────────────
function doPost(e) {
  try {
    const params = (e && e.parameter) || {};
    const action = String(params.action || "subscribe").toLowerCase();

    if (action === "star") {
      return _handleStar(params);
    }
    return _handleSubscribe(params, e);
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

function _handleSubscribe(params, e) {
  let email = String(params.email || "");
  if (!email && e && e.postData && e.postData.contents) {
    try { email = JSON.parse(e.postData.contents).email || ""; } catch (_) {}
  }
  email = email.trim().toLowerCase();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return _json({ ok: false, error: "invalid_email" });
  }
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  const data = sheet.getDataRange().getValues();
  const emails = new Set(data.slice(1).map(r => String(r[0] || "").trim().toLowerCase()));
  if (!emails.has(email)) {
    sheet.appendRow([email, new Date()]);
  }
  return _json({ ok: true });
}

function _handleStar(params) {
  // Loguea cada star/unstar a la hoja "stars". Cada fila = un evento, lo cual
  // permite contar populairidad por (cine, title, fecha, hora) o agregar por
  // título total. La hoja se autocrea con headers si no existe.
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName("stars");
  if (!sheet) {
    sheet = ss.insertSheet("stars");
    sheet.appendRow(["timestamp", "on", "key", "cine", "title", "fecha", "hora"]);
  }
  sheet.appendRow([
    new Date(),
    String(params.on || "1") === "1" ? 1 : 0,
    String(params.key || ""),
    String(params.cine || ""),
    String(params.title || ""),
    String(params.fecha || ""),
    String(params.hora || ""),
  ]);
  return _json({ ok: true });
}

function doOptions(e) {
  return ContentService.createTextOutput("");
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}


// ───── 2. Envío semanal ─────────────────────────────────────────────────
function sendNewsletter() {
  const weekStart = _nextOrSameMonday(new Date());
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 6);

  // Bajar cartelera
  const res = UrlFetchApp.fetch(CARTELERA_URL + "?t=" + Date.now(), { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    Logger.log("Cartelera fetch fail: " + res.getResponseCode());
    return;
  }
  const data = JSON.parse(res.getContentText());
  const screenings = data.screenings || [];

  const html = _buildEmailHtml(weekStart, weekEnd, screenings);
  const subject = SUBJECT_PREFIX + " " + _captionDates(weekStart, weekEnd);

  // Cargar suscriptores
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  const rows = sheet.getDataRange().getValues();
  const emails = rows.slice(1)
    .map(r => String(r[0] || "").trim())
    .filter(e => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e));

  Logger.log("Sending '" + subject + "' to " + emails.length + " subscribers");
  for (const email of emails) {
    try {
      MailApp.sendEmail({
        to: email,
        subject: subject,
        htmlBody: html,
        name: FROM_NAME,
      });
    } catch (err) {
      Logger.log("Fail " + email + ": " + err);
    }
  }
}

function _nextOrSameMonday(d) {
  const r = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  // getDay: 0=Sun, 1=Mon...
  const dow = r.getDay();
  const diff = dow === 0 ? 1 : (dow === 1 ? 0 : 8 - dow);
  r.setDate(r.getDate() + diff);
  return r;
}

function _captionDates(start, end) {
  const mS = MONTHS_ES[start.getMonth()];
  const mE = MONTHS_ES[end.getMonth()];
  if (start.getMonth() === end.getMonth()) {
    return "del " + start.getDate() + " al " + end.getDate() + " de " + mS;
  }
  return "del " + start.getDate() + " de " + mS + " al " + end.getDate() + " de " + mE;
}

function _isoDate(d) {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return d.getFullYear() + "-" + m + "-" + day;
}

function _escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function _buildEmailHtml(weekStart, weekEnd, screenings) {
  const when = _captionDates(weekStart, weekEnd);
  const weekSet = new Set();
  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart); d.setDate(d.getDate() + i);
    weekSet.add(_isoDate(d));
  }
  const byDay = {};
  for (const s of screenings) {
    if (weekSet.has(s.fecha)) {
      (byDay[s.fecha] = byDay[s.fecha] || []).push(s);
    }
  }
  for (const k of Object.keys(byDay)) {
    byDay[k].sort((a, b) => (a.hora || "99").localeCompare(b.hora || "99"));
  }

  // Reusable style strings — armados una sola vez para mantener el output
  // compacto sin sacrificar inline-styles (que es lo único que renderiza
  // consistente en Gmail/Outlook/Apple Mail).
  const SROW = 'border-bottom:1px solid ' + T_BORDER + ';font-size:13px;color:' + T_TEXT + ';vertical-align:top;';

  const parts = [
    '<div style="background:' + T_BG + ';color:' + T_TEXT + ';font-family:' + T_FONT + ';line-height:1.45;">',
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" bgcolor="' + T_BG
    + '" style="background:' + T_BG + ';border-collapse:collapse"><tr><td align="center" style="padding:28px 12px">',
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="900" '
    + 'style="max-width:900px;width:100%;background:' + T_BG + ';color:' + T_TEXT + ';'
    + 'font-family:' + T_FONT + ';line-height:1.45;text-align:left">',

    // Header — logo + brand
    '<tr><td style="padding:0 0 22px;border-bottom:1px solid ' + T_BORDER + '">',
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>',
    '<td valign="middle" style="padding-right:12px">',
    '<img src="' + LOGO_URL + '" alt="Si te digo" width="48" height="48" '
    + 'style="display:block;width:48px;height:auto;border:0">',
    '</td>',
    '<td valign="middle">',
    '<div style="font-size:18px;font-weight:700;letter-spacing:-0.01em;color:' + T_TEXT + '">'
    + _escapeHtml(BRAND_NAME) + '</div>',
    '<div style="font-size:12px;color:' + T_MUTED + ';margin-top:2px">Cartelera semanal — cines · Buenos Aires</div>',
    '</td></tr></table></td></tr>',

    // Intro
    '<tr><td style="padding:18px 0 4px;font-size:14px;color:' + T_TEXT + '">'
    + 'Programación de las salas de cine de la ciudad, semana ' + _escapeHtml(when) + '. '
    + '<span style="color:' + T_MUTED + ';font-size:13px">Tocá una película para ver director, año y duración en Letterboxd, o entrá a '
    + '<a href="' + SITE_URL + '" style="color:' + T_ACCENT + ';text-decoration:none">sitedigo.com</a> para todos los detalles.</span>'
    + '</td></tr>',

    '<tr><td style="padding:0 0 24px">',
  ];

  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart); d.setDate(d.getDate() + i);
    const iso = _isoDate(d);
    const films = byDay[iso] || [];
    const dayName = DAYS_ES[(d.getDay() + 6) % 7];
    parts.push(
      '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
      + 'style="border-collapse:collapse;margin:26px 0 10px;border-bottom:1px solid ' + T_BORDER + '"><tr>'
      + '<td style="font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:' + T_ACCENT + ';padding-bottom:6px">'
      + _escapeHtml(dayName + " " + d.getDate() + " de " + MONTHS_ES[d.getMonth()]) + '</td>'
      + '<td align="right" style="font-size:11px;color:' + T_MUTED + ';padding-bottom:6px">'
      + films.length + ' funciones</td></tr></table>'
    );
    if (!films.length) {
      parts.push('<div style="margin:6px 0 0;color:' + T_MUTED + ';font-size:13px">— sin funciones —</div>');
      continue;
    }
    if (films.length >= 8) {
      // 4 columnas — días llenos (8+ funciones)
      parts.push(_nColumnFilms(films, 4, SROW));
    } else if (films.length >= 4) {
      // 2 columnas — días intermedios
      parts.push(_nColumnFilms(films, 2, SROW));
    } else {
      // 1 columna — días con pocas funciones
      parts.push('<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse">');
      for (const s of films) parts.push(_renderFilmRow(s, SROW));
      parts.push('</table>');
    }
  }

  parts.push(
    '</td></tr>',
    '<tr><td style="padding-top:16px;border-top:1px solid ' + T_BORDER + ';font-size:12px;color:' + T_MUTED + '">'
    + 'Todas las funciones también en '
    + '<a href="' + SITE_URL + '" style="color:' + T_ACCENT + ';text-decoration:none">sitedigo.com</a> · '
    + '<a href="https://instagram.com/sitedigocine" style="color:' + T_ACCENT + ';text-decoration:none">@sitedigocine</a> en Instagram.'
    + '</td></tr>',
    '</table></td></tr></table></div>'
  );
  return parts.join("");
}


function _nColumnFilms(films, n, sRow) {
  // Distribuye las pelis equitativamente en N columnas, llenando primero
  // la columna 1, después la 2, etc. (lectura natural top-to-bottom).
  const perCol = Math.ceil(films.length / n);
  const cols = [];
  for (let i = 0; i < n; i++) {
    cols.push(films.slice(i * perCol, (i + 1) * perCol));
  }
  const widthPct = Math.floor(100 / n);
  const renderCol = (arr) => {
    return '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
      + 'style="border-collapse:collapse">'
      + arr.map(s => _renderFilmRow(s, sRow)).join("") + '</table>';
  };
  const cells = cols.map((arr, idx) => {
    // Padding entre columnas: derecho excepto última, izquierdo excepto primera
    const pl = idx === 0 ? 0 : 10;
    const pr = idx === n - 1 ? 0 : 10;
    return '<td valign="top" width="' + widthPct + '%" '
      + 'style="padding:0 ' + pr + 'px 0 ' + pl + 'px">' + renderCol(arr) + '</td>';
  }).join("");
  return (
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
    + 'style="border-collapse:collapse"><tr>' + cells + '</tr></table>'
  );
}


function _renderFilmRow(s, sRow) {
  // Versión compacta: 1 línea por peli (hora + cine + título). Si la peli
  // tiene letterboxd, el título linkea ahí para que el lector vea director /
  // año / duración / sinopsis sin tener que cargar todo eso en el mail
  // (Gmail clipea a 102KB y los detalles completos no entran en una semana
  // típica de 150+ funciones).
  const title = s.title_es || s.title_en || "(sin título)";
  const lb = s.letterboxd || "";
  const titleHtml = lb
    ? '<a href="' + _escapeHtml(lb) + '" style="color:' + T_TEXT + ';text-decoration:none;font-weight:500">' + _escapeHtml(title) + '</a>'
    : '<span style="font-weight:500">' + _escapeHtml(title) + '</span>';
  return (
    '<tr>'
    + '<td width="50" valign="top" style="padding:5px 10px 5px 0;' + sRow
    + 'font-weight:700;white-space:nowrap">' + _escapeHtml(s.hora || "??") + '</td>'
    + '<td valign="top" style="padding:5px 0;' + sRow + '">'
    + '<span style="display:inline-block;font-size:10px;color:' + T_MUTED + ';text-transform:uppercase;'
    + 'letter-spacing:.05em;border:1px solid ' + T_BORDER + ';padding:1px 6px;border-radius:3px;'
    + 'margin-right:6px;vertical-align:1px">' + _escapeHtml(s.cine || "") + '</span>'
    + titleHtml
    + '</td></tr>'
  );
}


// ───── 3. Tests útiles ────────────────────────────────────────────────
// Correr a mano desde Apps Script editor para verificar antes del trigger.
function previewNewsletter() {
  const weekStart = _nextOrSameMonday(new Date());
  const weekEnd = new Date(weekStart); weekEnd.setDate(weekEnd.getDate() + 6);
  const res = UrlFetchApp.fetch(CARTELERA_URL + "?t=" + Date.now());
  const data = JSON.parse(res.getContentText());
  const html = _buildEmailHtml(weekStart, weekEnd, data.screenings || []);
  Logger.log("subject: " + SUBJECT_PREFIX + " " + _captionDates(weekStart, weekEnd));
  Logger.log("body len: " + html.length);
  // Mandate a vos mismo para probar visualmente
  MailApp.sendEmail({
    to: Session.getActiveUser().getEmail(),
    subject: "[PREVIEW] " + SUBJECT_PREFIX + " " + _captionDates(weekStart, weekEnd),
    htmlBody: html,
    name: FROM_NAME,
  });
  Logger.log("Preview enviado a " + Session.getActiveUser().getEmail());
}

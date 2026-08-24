/**
 * Auditoría de la cartelera por mail — Google Apps Script.
 *
 * Va en un proyecto de Apps Script APARTE del newsletter, a propósito: acá no
 * hay ninguna función que le mande mail a nadie más que a vos. El proyecto del
 * newsletter tiene la lista de suscriptores y su propio trigger; este archivo
 * no lo toca ni lo importa.
 *
 * Por qué Apps Script y no GitHub Actions: mandar mail desde el runner pediría
 * guardar una contraseña de aplicación como secret del repo. Acá corre con tu
 * cuenta de Google y no hay ninguna credencial dada de alta en ningún lado.
 *
 * ──────────────────────────────────────────────────────────────────────
 * SETUP (una vez):
 *   1. script.google.com → Nuevo proyecto → nombralo "Auditoría cines"
 *      (NUEVO, no el del newsletter)
 *   2. Pegá este archivo entero, reemplazando el Code.gs vacío
 *   3. Ejecutar → sendAuditMail. Te pide permisos y te manda el informe de hoy
 *   4. Triggers (el reloj) → Add trigger:
 *        - Function: sendAuditMail
 *        - Source: Time-driven → Week timer → Monday → 10 AM-11 AM
 *      (el workflow corre 09:30 ART, así que a las 10 ya está el informe)
 *
 * SI EL MAIL NO LLEGA: correr `diagnosticarAuditMail` desde el editor y mirar
 * Ejecuciones → Registro. Dice cuál de las tres cosas se rompió: no hay
 * trigger, no se puede leer el informe, o no se resuelve el destinatario. El
 * paso 4 es el que más se olvida — sin trigger, sendAuditMail corre sólo
 * cuando la ejecutás vos, y el mail no llega nunca.
 * ──────────────────────────────────────────────────────────────────────
 */

const AUDIT_URL = "https://raw.githubusercontent.com/allerand/cines/main/data/audit.html";
// Vacío = tu propia casilla. No pongas acá una lista de nadie más.
const AUDIT_TO = "";

/**
 * A quién sale el mail.
 *
 * Session.getActiveUser() devuelve la casilla sólo cuando hay alguien usando
 * el script; disparado por el trigger del reloj, en cuentas de Gmail comunes
 * suele devolver "". Con el destinatario vacío MailApp tira excepción, el
 * trigger queda en rojo y no llega NADA — que es exactamente el síntoma de
 * "no me llega la auditoría", sin ninguna pista de por qué.
 * getEffectiveUser() es el dueño del script y sí resuelve bajo el trigger.
 */
function destinatario_() {
  if (AUDIT_TO) return AUDIT_TO;
  const activo = Session.getActiveUser().getEmail();
  if (activo) return activo;
  const efectivo = Session.getEffectiveUser().getEmail();
  if (efectivo) return efectivo;
  throw new Error("No pude resolver a quién mandarle el mail: poné tu " +
                  "dirección a mano en AUDIT_TO.");
}

function sendAuditMail() {
  const res = UrlFetchApp.fetch(AUDIT_URL + "?t=" + Date.now(), { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    // Antes esto era un `return` mudo. Pero el mail semanal es el latido de
    // todo esto: si un lunes no llega nada, no se distingue "el informe no se
    // pudo leer" de "el trigger está muerto". Así que cuando falla la lectura
    // igual sale un mail, que es la única forma de que se note.
    Logger.log("No se pudo leer el informe: HTTP " + res.getResponseCode());
    MailApp.sendEmail({
      to: destinatario_(),
      subject: "⚠️ Auditoría cartelera: no pude leer el informe",
      htmlBody: "No pude bajar <code>" + AUDIT_URL + "</code>: HTTP " +
                res.getResponseCode() + ".<br><br>Suele ser que el workflow " +
                "<code>audit.yml</code> dejó de commitear <code>data/audit.html</code>, " +
                "o que el repo pasó a privado (raw.githubusercontent contesta 404 " +
                "sin autenticación).",
      name: "Auditoría cartelera",
    });
    return;
  }
  const html = res.getContentText();

  // audit.py deja el veredicto en un comentario HTML para no tener que
  // re-parsear el informe sólo para armar el asunto.
  const mRes = html.match(/<!--\s*asunto:\s*(.*?)\s*-->/);
  const asunto = mRes ? mRes[1] : "Auditoría de cartelera";

  // Quién audita al auditor: si el informe no es de esta semana, el workflow
  // dejó de correr. Sin este chequeo llegaría el mismo informe viejo para
  // siempre, dando la falsa impresión de que está todo bien.
  const mFecha = html.match(/<!--\s*fecha:\s*(\d{4}-\d{2}-\d{2})\s*-->/);
  let aviso = "";
  if (mFecha) {
    const dias = Math.floor((Date.now() - new Date(mFecha[1] + "T12:00:00Z")) / 86400000);
    if (dias > 8) {
      aviso = "[informe de hace " + dias + " días] ";
      Logger.log("El informe tiene " + dias + " días: revisá el workflow audit.yml");
    }
  }

  const to = destinatario_();
  MailApp.sendEmail({
    to: to,
    subject: aviso + asunto,
    htmlBody: html,
    name: "Auditoría cartelera",
  });
  Logger.log("Enviado a " + to + ": " + asunto);
}

/**
 * Diagnóstico, para correr a mano desde el editor cuando el mail no llega.
 * Contesta las tres preguntas en orden, que son las tres cosas que se pueden
 * romper por separado: ¿hay trigger?, ¿se puede leer el informe?, ¿a quién
 * saldría el mail? Mirá el resultado en Ejecuciones → Registro.
 */
function diagnosticarAuditMail() {
  const triggers = ScriptApp.getProjectTriggers()
      .filter(t => t.getHandlerFunction() === "sendAuditMail");
  Logger.log(triggers.length
      ? "✅ Trigger configurado (" + triggers.length + ")"
      : "❌ NO hay trigger para sendAuditMail: el mail no se manda solo nunca. " +
        "Triggers → Add trigger → sendAuditMail, Time-driven, Week timer, lunes 10-11 AM.");

  const res = UrlFetchApp.fetch(AUDIT_URL + "?t=" + Date.now(), { muteHttpExceptions: true });
  const code = res.getResponseCode();
  Logger.log(code === 200 ? "✅ Informe legible (HTTP 200)"
                          : "❌ No se puede leer el informe: HTTP " + code);
  if (code === 200) {
    const m = res.getContentText().match(/<!--\s*fecha:\s*(\d{4}-\d{2}-\d{2})\s*-->/);
    Logger.log(m ? "   informe del " + m[1] : "   ⚠️ sin marcador de fecha");
  }

  try {
    Logger.log("✅ Saldría a: " + destinatario_());
  } catch (e) {
    Logger.log("❌ " + e.message);
  }
  Logger.log("Cuota de mails que queda hoy: " + MailApp.getRemainingDailyQuota());
}

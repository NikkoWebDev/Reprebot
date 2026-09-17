// Handler de messages.upsert.
//
// Todas las reglas son fail-closed: ante cualquier duda, no responde. El unico
// grupo valido es config.groupJid (resuelto por index.js); sin eso solo avisa
// como configurarlo.

import { jidNormalizedUser } from '@whiskeysockets/baileys';
import { preguntar } from './backend.js';

const DEDUPE_TTL_MS = 5 * 60 * 1000;
const DEDUPE_CLEAN_EVERY_MS = 60 * 1000;
const GRUPO_SIN_CONFIG_MS = 10 * 60 * 1000;
const ERROR_NOTICE_MS = 5 * 60 * 1000;
const MAX_MSG_AGE_SECONDS = 60;
const MIN_PREGUNTA_CHARS = 3;

function extraerTexto(msg) {
  const m = msg?.message;
  if (!m) return '';
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    ''
  ).trim();
}

function contextInfo(msg) {
  const m = msg?.message || {};
  return (
    m.extendedTextMessage?.contextInfo ||
    m.imageMessage?.contextInfo ||
    m.videoMessage?.contextInfo ||
    null
  );
}

function mencionaAlBot(msg, botJid) {
  if (!botJid) return false;
  const menciones = contextInfo(msg)?.mentionedJid || [];
  return menciones.some((jid) => jid && jidNormalizedUser(jid) === botJid);
}

function quitarMenciones(texto) {
  return texto.replace(/@\d{6,}/g, ' ');
}

function aplicarPrefijo(texto, triggers) {
  const t = texto.trim();
  for (const prefijo of triggers) {
    if (prefijo && t.toLowerCase().startsWith(prefijo.toLowerCase())) {
      return { aplicado: true, texto: t.slice(prefijo.length).trim() };
    }
  }
  return { aplicado: false, texto: t };
}

function normalizarEspacios(texto) {
  return texto.replace(/\s+/g, ' ').trim();
}

function recortar(texto, maxChars) {
  const limite = Number(maxChars) > 0 ? Math.floor(maxChars) : 1800;
  if (texto.length <= limite) return texto;
  const corte = texto.lastIndexOf('. ', limite);
  if (corte > 0) return texto.slice(0, corte + 1);
  return texto.slice(0, limite);
}

function fuentesUnicas(sources) {
  const lista = [];
  const vistos = new Set();
  for (const s of sources || []) {
    const nombre = typeof s?.doc_name === 'string' ? s.doc_name.trim() : '';
    if (!nombre || vistos.has(nombre)) continue;
    vistos.add(nombre);
    const url = typeof s?.source_url === 'string' ? s.source_url.trim() : '';
    lista.push(url ? `${nombre} (${url})` : nombre);
    if (lista.length >= 3) break;
  }
  return lista;
}

function formatearRespuesta(payload, maxChars) {
  let texto = typeof payload?.answer === 'string' ? payload.answer.trim() : '';
  if (!texto) texto = 'El backend no devolvio respuesta.';
  const fuentes = fuentesUnicas(payload?.sources);
  if (fuentes.length > 0) texto += `\n\n_Fuentes: ${fuentes.join(', ')}_`;
  return recortar(texto, maxChars);
}

// Devuelve la pregunta lista para mandar al backend, o null si el mensaje no
// dispara nada.
function textoPregunta(msg, config, botJid) {
  const crudo = extraerTexto(msg);
  if (!crudo) return null;

  const porMencion = mencionaAlBot(msg, botJid);
  const { aplicado, texto } = aplicarPrefijo(crudo, config.triggers || []);
  if (!porMencion && !aplicado) return null;

  return normalizarEspacios(quitarMenciones(texto));
}

export function crearHandler({ sock, config, log, grupos }) {
  const dedupe = new Map();
  const cooldowns = new Map();
  const ventanaGlobal = [];
  const avisoGrupo = new Map();
  const avisoError = new Map();
  const gruposLogueados = new Set();
  let ultimaLimpieza = Date.now();

  function jidDelBot() {
    return sock.user?.id ? jidNormalizedUser(sock.user.id) : null;
  }

  function limpiarDedupe(ahora) {
    if (ahora - ultimaLimpieza < DEDUPE_CLEAN_EVERY_MS) return;
    ultimaLimpieza = ahora;
    for (const [id, ts] of dedupe) {
      if (ahora - ts > DEDUPE_TTL_MS) dedupe.delete(id);
    }
    const ventanaCooldown = Math.max((Number(config.cooldownSeconds) || 20) * 1000, 60 * 1000);
    for (const [jid, ts] of cooldowns) {
      if (ahora - ts > ventanaCooldown) cooldowns.delete(jid);
    }
  }

  // Sin grupo resuelto: loguea el JID una vez por grupo y, si de verdad
  // llamaron al bot, pide configurarlo maximo una vez cada 10 min por grupo.
  async function manejarGrupoDesconocido(msg, remoteJid, ahora) {
    const subject = grupos.get(remoteJid) || '';
    if (!gruposLogueados.has(remoteJid)) {
      gruposLogueados.add(remoteJid);
      log.warn(
        `Grupo detectado: ${remoteJid}${subject ? ` ("${subject}")` : ''}. ` +
          'Configura WA_GROUP_NAME o WA_GROUP_JID.',
      );
    }

    const texto = textoPregunta(msg, config, jidDelBot());
    if (texto === null) return;

    const ultimo = avisoGrupo.get(remoteJid) || 0;
    if (ahora - ultimo < GRUPO_SIN_CONFIG_MS) return;
    avisoGrupo.set(remoteJid, ahora);

    await sock.sendMessage(
      remoteJid,
      {
        text:
          `Todavia no hay grupo configurado. Pasa WA_GROUP_JID=${remoteJid} ` +
          'o pon WA_GROUP_NAME en las variables del servicio.',
      },
      { quoted: msg },
    );
  }

  async function manejarErrorBackend(msg, remoteJid, ahora, err) {
    log.error(`Fallo consultando el backend: ${err?.message || err}`);
    const ultimo = avisoError.get(remoteJid) || 0;
    if (ahora - ultimo < ERROR_NOTICE_MS) return;
    avisoError.set(remoteJid, ahora);
    try {
      await sock.sendMessage(
        remoteJid,
        { text: 'No pude consultar el backend ahora mismo. Intenta de nuevo en un momento.' },
        { quoted: msg },
      );
    } catch (errAviso) {
      log.error(`No pude avisar del fallo: ${errAviso?.message || errAviso}`);
    }
  }

  async function procesar(msg) {
    if (!msg?.key || msg.key.fromMe) return;

    const remoteJid = msg.key.remoteJid;
    // Nunca responde en privado.
    if (!remoteJid || !remoteJid.endsWith('@g.us')) return;

    const ahora = Date.now();
    limpiarDedupe(ahora);

    // Un solo grupo.
    if (config.groupJid) {
      if (remoteJid !== config.groupJid) return;
    } else {
      await manejarGrupoDesconocido(msg, remoteJid, ahora);
      return;
    }

    // Sync de historial: ignora lo que llega viejo.
    if (ahora / 1000 - Number(msg.messageTimestamp) > MAX_MSG_AGE_SECONDS) return;

    // Dedupe por id (Baileys puede repetir en reconexiones).
    const id = msg.key.id;
    if (id) {
      if (dedupe.has(id)) return;
      dedupe.set(id, ahora);
    }

    const texto = textoPregunta(msg, config, jidDelBot());
    if (texto === null) return;

    const senderJid = msg.key.participant || remoteJid;

    if (texto.length < MIN_PREGUNTA_CHARS) {
      await sock.sendMessage(
        remoteJid,
        { text: 'Dime la pregunta despues del comando, por ejemplo: !repre como inscribo materias?' },
        { quoted: msg },
      );
      return;
    }

    // Throttle: cooldown por usuario y tope global por minuto.
    const cooldownMs = (Number(config.cooldownSeconds) || 20) * 1000;
    if (ahora - (cooldowns.get(senderJid) || 0) < cooldownMs) {
      log.info(`Cooldown activo para ${senderJid}; ignoro.`);
      return;
    }
    const maxPorMinuto = Number(config.maxPerMinute) || 6;
    while (ventanaGlobal.length > 0 && ahora - ventanaGlobal[0] > 60 * 1000) {
      ventanaGlobal.shift();
    }
    if (ventanaGlobal.length >= maxPorMinuto) {
      log.info('Tope global por minuto alcanzado; ignoro.');
      return;
    }
    cooldowns.set(senderJid, ahora);
    ventanaGlobal.push(ahora);

    try {
      await sock.sendPresenceUpdate('composing', remoteJid);
      const data = await preguntar(texto, msg.pushName || '');
      await sock.sendMessage(
        remoteJid,
        { text: formatearRespuesta(data, config.maxChars), mentions: [senderJid] },
        { quoted: msg },
      );
    } catch (err) {
      await manejarErrorBackend(msg, remoteJid, ahora, err);
    }
  }

  return async function handler(evento) {
    try {
      if (!evento || evento.type !== 'notify') return;
      for (const msg of evento.messages || []) {
        try {
          await procesar(msg);
        } catch (err) {
          // Un mensaje malo no puede tumbar el proceso ni frenar al resto.
          log.error(`Error procesando mensaje: ${err?.message || err}`);
        }
      }
    } catch (err) {
      log.error(`Error en messages.upsert: ${err?.message || err}`);
    }
  };
}

# Reprebot WhatsApp

Puente entre WhatsApp y el backend de Reprebot. Se conecta a un numero
secundario con Baileys, escucha **un solo grupo**, y cuando etiquetan al bot o
usan un prefijo le pasa la pregunta al backend FastAPI y responde en el grupo
citando el mensaje.

## Requisitos

- Node 20 o superior.
- Un numero secundario de WhatsApp. **Riesgo de ban**: Baileys es una libreria
  no oficial; WhatsApp puede suspender el numero. No uses tu numero principal.

## Instalacion y arranque local

```bash
cd apps/whatsapp
npm install --no-audit --no-fund
cp .env.example .env
npm start
```

El arranque imprime el QR en la consola (o espera a que aparezca). La sesion
queda guardada en `auth/`.

## Emparejar

1. Abre WhatsApp en el telefono del numero secundario.
2. Ajustes > Dispositivos vinculados > Vincular un dispositivo.
3. Escanea el QR de los logs. Si ya no lo tienes, abre
   `http://localhost:3000/qr?token=<WA_QR_TOKEN>` en texto plano.

Cada deploy o reinicio en Render pide QR otra vez, porque el disco es efimero.

## Obtener el JID del grupo

Deja `WA_GROUP_NAME` y `WA_GROUP_JID` vacios, arranca la app y mira los logs:
por cada grupo que ve escribe el `subject` y el JID (`12036...@g.us`). Copia el
que corresponda.

## Variables de entorno

| Variable | Default | Descripcion |
| --- | --- | --- |
| `BACKEND_URL` | `http://127.0.0.1:8000` | URL publica del backend. En Render free tiene que ser la publica (no hay red privada en free). |
| `WHATSAPP_API_KEY` | vacio | Mismo valor que `WHATSAPP_API_KEY` del backend. Vacio = no manda el header `X-Api-Key`. |
| `WA_GROUP_NAME` | vacio | Nombre exacto del grupo, comparado case-insensitive y sin espacios extra. |
| `WA_GROUP_JID` | vacio | JID del grupo (`12036...@g.us`). Tiene prioridad sobre el nombre. |
| `WA_TRIGGERS` | `!repre,/repre` | Prefijos que disparan respuesta, separados por coma. |
| `WA_COOLDOWN_SECONDS` | `20` | Espera por usuario entre respuestas. |
| `WA_MAX_PER_MINUTE` | `6` | Tope global de respuestas por minuto (ventana deslizante). |
| `WA_MAX_CHARS` | `1800` | Largo maximo de la respuesta. |
| `WA_KEEPALIVE` | `false` | Si es `true`/`1` y existe `RENDER_EXTERNAL_URL`, se auto-pinguea cada 10 min. |
| `WA_QR_TOKEN` | vacio | Clave para leer `/qr?token=...`. Sin esto `/qr` devuelve 403 y el QR solo sale en los logs. |
| `PORT` | `3000` | Puerto del servidor HTTP. |
| `LOG_LEVEL` | `warn` | Nivel de pino. Baileys es muy verboso; `warn` no inunda los logs. |

Si `WA_GROUP_NAME` y `WA_GROUP_JID` quedan vacios, el bot no responde a nadie
pero loguea el JID de los grupos que ve.

## Despliegue en Render

El servicio ya esta declarado en `render.yaml` (`reprebot-whatsapp`, runtime
Docker, plan free, healthcheck `/health`).

- El `Dockerfile` usa `node:20-slim` e instala `git`: la dependencia `libsignal`
  de Baileys se baja por `git+https` y sin git el install falla.
- Health check: `GET /health` devuelve `{ ok, connected, group, groupName }`.
- Disco efimero: la carpeta `auth/` se pierde en cada deploy o reinicio, asi que
  hay que volver a escanear el QR.
- Cuota: los free tienen 750 horas-instancia al mes por workspace. Con
  `WA_KEEPALIVE=true` el servicio nunca duerme, y un mes son ~730 h, o sea que
  se come casi toda la cuota. Si conviven con el backend en free, Render puede
  suspenderlos al final del mes.

## Comportamiento

- Responde en un solo grupo: el de `WA_GROUP_JID`, o el que coincida con
  `WA_GROUP_NAME`. Si hay varios grupos con el mismo nombre, no responde hasta
  que se fije el JID.
- Disparadores: mencion al bot (`@Reprebot`) o que el texto empiece con alguno
  de `WA_TRIGGERS`.
- Nunca responde en privado.
- Descarta mensajes de mas de 60 s (el sync de historial) y deduplica por id.
- Throttle: `WA_COOLDOWN_SECONDS` por usuario y `WA_MAX_PER_MINUTE` global. Si se
  excede, calla.
- Cita el mensaje original y menciona a quien pregunto.
- Si el backend falla, avisa como maximo una vez cada 5 min por grupo.
- `GET /qr?token=<WA_QR_TOKEN>` devuelve el ultimo QR en texto plano (o `sin qr`). Sin `WA_QR_TOKEN` responde 403.

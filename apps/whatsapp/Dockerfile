# libsignal viene como dep git+https en Baileys y npm la reescribe a ssh://,
# que en un build sin llaves falla. El override en package.json la baja del
# registry npm (misma version 6.0.0), asi el install no toca git.
FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY src/ ./src/

ENV PORT=3000
EXPOSE 3000

CMD ["node", "src/index.js"]
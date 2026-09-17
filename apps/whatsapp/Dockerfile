FROM node:20-slim

# libsignal (dependencia de Baileys) se baja por git+https y npm lo reescribe a
# ssh (por eso sin credenciales el build falla con "ssh: not found"). Con
# insteadOf se fuerza https anonimo, que sirve para repos publicos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && git config --global url."https://github.com/".insteadOf "ssh://git@github.com/" \
    && git config --global url."https://github.com/".insteadOf "git@github.com:" \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY src/ ./src/

ENV PORT=3000
EXPOSE 3000

CMD ["node", "src/index.js"]

FROM node:20-slim

# libsignal (dependencia de Baileys) se baja por git+https; sin git falla el install.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY src/ ./src/

ENV PORT=3000
EXPOSE 3000

CMD ["node", "src/index.js"]

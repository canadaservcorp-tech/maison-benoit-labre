FROM node:20-bullseye-slim

WORKDIR /app

ENV NODE_ENV=production

# Build tools for better-sqlite3 native module
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 make g++ \
  && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

EXPOSE 4000

CMD ["node", "server.js"]

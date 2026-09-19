FROM node:24-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends openssl curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm install

COPY prisma ./prisma
COPY prisma.config.ts prisma7.config.ts ./
RUN npx prisma generate

COPY . .

EXPOSE 8000

CMD ["node", "--experimental-strip-types", "src/server.js"]

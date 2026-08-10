FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# `node` (uid 1000) ships with the base image. Running the server as root buys
# nothing — it serves a prebuilt bundle and owns no persistent state — and costs
# the usual root-in-container blast radius. --chown so `next start` can still
# write its own cache under .next/.
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/package.json ./package.json
COPY --from=builder --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["npm", "start"]

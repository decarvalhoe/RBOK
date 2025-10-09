# syntax=docker/dockerfile:1

ARG NODE_VERSION=18
FROM node:${NODE_VERSION}-alpine AS base

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci

COPY webapp/ ./

FROM base AS dev
CMD ["npm", "run", "dev"]

FROM base AS builder
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_AI_GATEWAY_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_AI_GATEWAY_URL=${NEXT_PUBLIC_AI_GATEWAY_URL}
RUN npm run build

FROM node:${NODE_VERSION}-alpine AS production
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app ./
RUN npm ci --omit=dev

ARG PORT=3000
ENV PORT=${PORT}
EXPOSE ${PORT}

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/package.json ./package.json
COPY --from=deps /app/node_modules ./node_modules
EXPOSE 3000
CMD ["npm", "run", "start"]

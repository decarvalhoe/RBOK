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

CMD ["npm", "run", "start"]

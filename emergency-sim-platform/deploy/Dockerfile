# 单容器部署：Node 服务同时提供前端静态文件与求解 API
#   docker build -f deploy/Dockerfile -t emergency-sim .
#   docker run -p 8787:8787 emergency-sim      → http://localhost:8787/
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm test

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=8787 STATIC_DIR=/app/dist DATA_DIR=/app/dist/data
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist
COPY --from=build /app/src/engine ./src/engine
COPY --from=build /app/server ./server
EXPOSE 8787
CMD ["node", "server/index.js"]

FROM node:24.19.0-alpine AS build
WORKDIR /app
RUN npm install --global npm@11.17.0 --ignore-scripts
COPY apps/web/package*.json apps/web/.npmrc ./
RUN npm ci --ignore-scripts
COPY apps/web/ ./
RUN npm run build
FROM nginxinc/nginx-unprivileged:1.28.0-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER 101:101
ENTRYPOINT ["nginx", "-g", "daemon off;"]

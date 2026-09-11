FROM node:20.17-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN addgroup -g 1001 appgroup && adduser -D -u 1001 -G appgroup appuser
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i -E 's#pid[[:space:]]+/(var/)?run/nginx\.pid;#pid /tmp/nginx/nginx.pid;#' /etc/nginx/nginx.conf \
    && chown -R appuser:appgroup /usr/share/nginx/html /var/cache/nginx /var/log/nginx /etc/nginx \
    && mkdir -p /tmp/nginx \
    && chown -R appuser:appgroup /tmp/nginx
USER appuser
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]

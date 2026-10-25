FROM node:24-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.28-alpine

ENV API_UPSTREAM=http://api:8000

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.sh /docker-entrypoint-wait.sh
COPY --from=build /app/build/client /usr/share/nginx/html

RUN chmod +x /docker-entrypoint-wait.sh

ENTRYPOINT ["/docker-entrypoint-wait.sh"]
CMD ["nginx", "-g", "daemon off;"]
EXPOSE 80

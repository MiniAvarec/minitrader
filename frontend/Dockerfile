## Build stage — install deps + produce static bundle.
FROM node:20-alpine AS build
WORKDIR /code
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

## Runtime stage — nginx serves the static bundle and proxies /api + /ws
## to the backend container on the internal docker network.
FROM nginx:1.27-alpine AS runtime
COPY --from=build /code/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

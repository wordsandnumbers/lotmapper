# Build stage
FROM node:20-alpine as build

ARG BUILD_SHA=dev
ARG SEMVER=0.0.0
ENV VITE_APP_VERSION=v${SEMVER}+git-${BUILD_SHA}

WORKDIR /app

COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

ARG BUILD_SHA=dev
ARG SEMVER=0.0.0
LABEL org.opencontainers.image.revision=${BUILD_SHA}
LABEL org.opencontainers.image.version=${SEMVER}

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

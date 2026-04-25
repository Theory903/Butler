# Butler Mobile — Expo Production Launcher
# Aligned with Oracle-Grade v3.0

FROM node:20-alpine

# Install system dependencies
RUN apk add --no-cache bash

# Set non-interactive environment for Expo
ENV CI=1
ENV EXPO_NON_INTERACTIVE=1

WORKDIR /app

# Install @expo/ngrok globally to prevent interactive prompts
RUN npm install -g @expo/ngrok@^4.1.0

# Copy dependency manifests
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Expose Expo ports
EXPOSE 8081
EXPOSE 19000
EXPOSE 19001
EXPOSE 19002

# The entrypoint is defined in docker-compose.yml: npx expo start -- --tunnel
# But we'll provide a default here as well.
CMD ["npx", "expo", "start", "--tunnel"]


FROM node:20-alpine
RUN apk add --no-cache iproute2
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
ENV PORT=3000
EXPOSE 3000
CMD ["node", "index.js"]

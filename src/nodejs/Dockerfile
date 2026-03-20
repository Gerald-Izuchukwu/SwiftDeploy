FROM node:18-alpine

WORKDIR /app

COPY package*.json /app

RUN npm ci 

COPY app.js /app

RUN addgroup -S devgroup && adduser -S dev -G devgroup && chown -R dev:devgroup /app

USER dev

ENV MODE=stable 
ENV PORT=3000 
ENV VERSION=1.0

EXPOSE 3000

CMD ["node", "app.js"]

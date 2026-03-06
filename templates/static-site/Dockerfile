FROM nginx:alpine
RUN apk add --no-cache iproute2
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY . /usr/share/nginx/html
ENV PORT=3000
EXPOSE 3000

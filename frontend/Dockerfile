FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/
COPY pages/ /usr/share/nginx/html/pages/
COPY css/ /usr/share/nginx/html/css/
COPY js/ /usr/share/nginx/html/js/
COPY static/ /usr/share/nginx/html/static/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

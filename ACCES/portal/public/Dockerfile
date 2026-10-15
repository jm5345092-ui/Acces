# Portal web (PHP) — se despliega en Railway como servicio "portal", separado del
# backend Node ("server"). Solo sirve estas páginas; toda la lógica va por la API.
FROM php:8.2-apache

COPY . /var/www/html/

# Reverse-proxy /webserver/ to the apklab-api/apklab-frontend services (see
# webserver-proxy.conf) so the APK decompiler lives under the portal's own
# domain instead of needing a separate subdomain/public service.
RUN a2enmod proxy proxy_http rewrite \
 && sed -i '/<VirtualHost/r /var/www/html/webserver-proxy.conf' /etc/apache2/sites-available/000-default.conf \
 && rm /var/www/html/webserver-proxy.conf

# Railway asigna el puerto en $PORT; Apache lee la variable directamente en su config.
RUN sed -i 's/^Listen 80$/Listen ${PORT}/' /etc/apache2/ports.conf \
 && sed -i 's/<VirtualHost \*:80>/<VirtualHost *:${PORT}>/' /etc/apache2/sites-available/000-default.conf

# En Railway reaparecen mpm_event/mpm_worker (borrados en una capa anterior de la imagen)
# y Apache aborta con "More than one MPM loaded". Se dejan vacíos para que solo cargue prefork.
RUN a2dismod mpm_event mpm_worker 2>/dev/null || true \
 && a2enmod mpm_prefork \
 && for m in mpm_event mpm_worker; do : > /etc/apache2/mods-enabled/$m.load; : > /etc/apache2/mods-enabled/$m.conf; done

ENV PORT=80
EXPOSE 80

CMD ["apache2-foreground"]

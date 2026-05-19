# lubimovka-readers
A platform for readers to vote and comment on plays for the Lubimovka project

# How to run?

## Production deployment

For production deployment, you need to create a .env file:

```
SECRET_KEY="<strong-random-key>"
FERNET_KEY="<strong-random-key>" 
ALLOWED_HOSTS=yourdomain1.com,yourdomain2.com,yourserverip
CSRF_TRUSTED_ORIGINS=https://yourdomain1.com,https://yourdomain2.com
DEBUG=False

DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=db
DB_PORT=5432
```

Create a docker-compose.yml file:

```
services:
  db:
    image: postgres:15-alpine
    container_name: lubimovka_db
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ${DB_NAME:-lubimovka_db}
      POSTGRES_USER: ${DB_USER:-postgres}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-postgres}
  web:
    image: ghcr.io/alytidae/lubimovka-readers:latest
    container_name: lubimovka_web
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      DB_HOST: db
      DB_PORT: 5432
    depends_on:
      - db
volumes:
  postgres_data:
```

And run:

```
docker compose up -d 
docker compose exec web uv run python manage.py migrate
docker compose exec web uv run python manage.py createsuperuser
```

The app is served by Gunicorn on port 8000 and static files are served via WhiteNoise, so no separate Nginx is needed for static files, but you would probably still want to put a reverse proxy in front.

## Local development

For local development, you need to clone the repo and create a .env file:

```
SECRET_KEY="<strong-random-key>"
FERNET_KEY="<strong-random-key>" 
ALLOWED_HOSTS=localhost
CSRF_TRUSTED_ORIGINS=http://localhost
DEBUG=True

DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=127.0.0.1
DB_PORT=5432
```

and then run:

```
docker compose up --build

docker compose exec web uv run python manage.py migrate

docker compose exec web uv run python manage.py createsuperuser
```

Since there is a docker-compose.override.yml file, Django will execute using runserver and changes in the code will apply immediately.


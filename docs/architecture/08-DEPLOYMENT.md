# Deployment Architecture

## Runtime Topology

```
                  ┌────────────┐
   Users ────────►│   Nginx    │◄──── TLS :443
                  └─────┬──────┘
            ┌───────────┼───────────┐
            ▼           ▼           ▼
       frontend     backend API   /ws proxy
                    ┌───┴───┐
                    ▼       ▼
               PostgreSQL  Redis
                    ▲       ▲
                    │       │
                 Celery ◄── RabbitMQ
                 workers
```

## Compose Services

- `nginx`  
- `frontend` (or static volume served by nginx)  
- `api`  
- `worker`  
- `beat` (optional schedules for metrics)  
- `postgres`  
- `redis`  
- `rabbitmq`  

## Installer Responsibilities (`install.sh`)

1. Verify Ubuntu (22.04/24.04)  
2. Create system user `netatlas`  
3. Install Docker Engine + Compose plugin  
4. Create `/opt/netatlas` directories  
5. Generate TLS certs + master key if missing  
6. Write `.env` with secure random secrets  
7. `docker compose pull/build && up -d`  
8. Install systemd unit `netatlas.service`  
9. Wait for `/readyz` health  
10. Print admin bootstrap instructions  

## Offline Operation

Images and frontend vendor libs are shipped with the release. No Google Fonts, no CDN, no external API calls from the product runtime.

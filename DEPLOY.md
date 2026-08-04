# Desplegar a producción

Producción son **dos sitios distintos** y se despliegan por separado:

| Parte | Dónde vive | Cómo llega |
|---|---|---|
| Panel (front) | Firebase Hosting → https://simulacros-3995d.web.app | `npm run build` + `firebase deploy` desde tu portátil |
| API (backend) | VM de Google, contenedor `simulacros_api` | `git pull` + `build` + `up` por SSH |

La API responde en `https://simulacros.pdaaia.com` (Caddy hace de proxy al 8002).
Si solo tocas ficheros de `frontend/`, no hace falta tocar la VM. Si solo tocas
`backend/`, no hace falta desplegar el front.

---

## 1. Subir el código (desde tu portátil)

```bash
cd C:\Users\MAGISTER\Desktop\simulacros\magister-simulacros
git add -A
git commit -m "descripcion del cambio"
git push origin main
```

---

## 2. Front → Firebase

El build necesita las dos variables: `NEXT_OUTPUT=export` genera el HTML estático
en `frontend/out`, y `NEXT_PUBLIC_API_URL` queda **incrustada en el JavaScript**
(no se lee en runtime, así que si te la dejas, el panel apuntará a localhost).

PowerShell:

```powershell
cd C:\Users\MAGISTER\Desktop\simulacros\magister-simulacros\frontend
$env:NEXT_OUTPUT="export"; $env:NEXT_PUBLIC_API_URL="https://simulacros.pdaaia.com"; npm run build
cd ..
firebase deploy --only hosting
```

Git Bash:

```bash
cd ~/Desktop/simulacros/magister-simulacros/frontend
NEXT_OUTPUT=export NEXT_PUBLIC_API_URL=https://simulacros.pdaaia.com npm run build
cd ..
firebase deploy --only hosting
```

Después, en el navegador: **Ctrl+Shift+R**. Sin eso puedes seguir viendo la
versión anterior, porque el JavaScript se cachea.

---

## 3. Backend → VM

```bash
ssh miguel@IP-DE-LA-VM
cd /srv/projects/simulacros
git pull origin main
docker-compose -f docker-compose.backend.yml build api
docker-compose -f docker-compose.backend.yml up -d --no-deps api
```

Tres cosas que hay que tener presentes:

- **Siempre `-f docker-compose.backend.yml`.** El `docker-compose.yml` a secas es
  el de desarrollo local: busca un `backend/.env` que en la VM no existe y falla.
- **El `build` no es opcional.** El código se copia dentro de la imagen al
  construirla; el contenedor no lee del disco. Si haces solo `up`, responde
  `simulacros_api is up-to-date` y sigues con el código viejo. El `up` bueno dice
  `Recreating simulacros_api ... done`.
- **Las migraciones se aplican solas.** `start.sh` ejecuta `alembic upgrade head`
  al arrancar. No hay que lanzarlas a mano.

`--no-deps` evita recrear el Postgres, que no cambia.

---

## 4. Comprobar que ha entrado

```bash
# La API responde
curl -s https://simulacros.pdaaia.com/health          # {"status":"ok"}

# Las migraciones están al día
docker-compose -f docker-compose.backend.yml exec api alembic current

# El arranque fue limpio
docker-compose -f docker-compose.backend.yml logs --tail 40 api
```

Para confirmar que un cambio concreto está dentro del contenedor, busca algo que
solo exista en el código nuevo:

```bash
docker-compose -f docker-compose.backend.yml exec api grep -c ALGO_DEL_CAMBIO app/api/analyses.py
```

---

## 5. Atajo: probar un script sin reconstruir

Para los `scripts/` de diagnóstico no hace falta build ni reinicio (cero corte
para quien esté llamando en ese momento):

```bash
docker cp backend/scripts/EL_SCRIPT.py simulacros_api:/app/scripts/
docker-compose -f docker-compose.backend.yml exec api python -m scripts.EL_SCRIPT
```

Esto **no** vale para cambios en `app/`: eso sí necesita `build`.

---

## Si algo sale mal

```bash
docker-compose -f docker-compose.backend.yml logs --tail 100 api
```

Volver a la versión anterior:

```bash
git log --oneline -5          # localiza el commit bueno
git reset --hard COMMIT
docker-compose -f docker-compose.backend.yml build api
docker-compose -f docker-compose.backend.yml up -d --no-deps api
```

Las migraciones ya aplicadas no se deshacen con eso, pero añadir una tabla o una
columna no rompe al código antiguo: simplemente las ignora.

Backup de la base antes de cualquier cosa destructiva:

```bash
docker exec simulacros_postgres pg_dump -U magister magister_simulacros > ~/simulacros-$(date +%F-%H%M).sql
```

---

> `DEPLOY_RENDER.md` y `render.yaml` son de un despliegue anterior en Render.
> La producción actual es la de este documento.

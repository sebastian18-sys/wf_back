# ====== base ======
# FROM node:20-bookworm AS base

# ENV TZ=America/Lima

# # Instalar Python3 + pip y toolchain para libs científicas (cvxpy, numpy)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     python3 python3-pip python3-venv \
#     build-essential gfortran pkg-config \
#     libblas-dev liblapack-dev libatlas-base-dev \
#     libffi-dev git \
#   && rm -rf /var/lib/apt/lists/*

# WORKDIR /app

# # Copiamos requirements de Python y las instalamos en venv (opcional)
# COPY scripts/python/requirements.txt ./scripts/python/requirements.txt
# RUN python3 -m venv /opt/venv && . /opt/venv/bin/activate \
#   && pip install --upgrade pip \
#   && pip install -r scripts/python/requirements.txt

# ENV PATH="/opt/venv/bin:${PATH}"

# # Copia Node deps
# COPY package*.json ./
# RUN npm ci

# # Copia el resto del código
# COPY . .

FROM node:20-slim AS base

ENV TZ=America/Lima

WORKDIR /app

# Python + libs runtime (sin compilar)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    libgfortran5 libopenblas0 liblapack3 \
 && rm -rf /var/lib/apt/lists/*

COPY scripts/python/requirements.txt ./scripts/python/requirements.txt
RUN python3 -m venv /opt/venv && . /opt/venv/bin/activate \
 && pip install --upgrade pip \
 && pip install --only-binary=:all: -r scripts/python/requirements.txt
ENV PATH="/opt/venv/bin:${PATH}"

COPY package*.json ./
RUN npm ci
COPY . .


# ====== development ======
FROM base AS development

COPY deploy/default_dev.config /etc/nginx/conf.d/default.config
ENV NODE_ENV=development
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ====== production ======
FROM base AS production

COPY deploy/default.config /etc/nginx/conf.d/default.config
ENV NODE_ENV=production
RUN npm prune --production
EXPOSE 3000
CMD ["npm", "start"]

# # ====== NGINX ======
# FROM nginx:latest AS runtime

# ENV TZ=America/Lima
# COPY --from=production /app/dist /usr/share/nginx/html
# COPY ./deploy/default.config /etc/nginx/conf.d/default.config

RUN env
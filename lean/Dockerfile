# Lean 4 + Mathlib + REPL. Se construye una vez; la imagen es el entorno de verificacion.
#
#   docker build -t mathagents-lean:v4.15.0 lean/
#   docker run --rm mathagents-lean:v4.15.0 python3 -m src.verify --smoke
#
# El build tarda ~15-25 min la primera vez (descarga del cache de Mathlib, varios GB).
# NO compila Mathlib desde fuente: eso son horas (decisions.md D1.3).

FROM ubuntu:24.04

ARG LEAN_VERSION=v4.15.0
ARG MATHLIB_TAG=v4.15.0
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/root/.elan/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl git ca-certificates build-essential python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# elan: gestor de toolchains de Lean.
RUN curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
      -o /tmp/elan-init.sh \
 && sh /tmp/elan-init.sh -y --default-toolchain "leanprover/lean4:${LEAN_VERSION}" \
 && rm /tmp/elan-init.sh \
 && lean --version

WORKDIR /app/mathproj
COPY lean-toolchain lakefile.lean MathProj.lean ./

# Cache binario de Mathlib. Sin esto el build son horas de CPU.
RUN lake update -R \
 && lake exe cache get \
 && lake build

# Resolver el tag a commit y dejarlo registrado: es lo que se cita en el informe (RNF-2).
RUN git -C .lake/packages/mathlib rev-parse HEAD > /app/mathlib-commit.txt \
 && cat /app/mathlib-commit.txt

# REPL: proceso de larga vida que acepta codigo Lean por stdin en JSON.
# Se fija al mismo tag que el toolchain: el master del REPL va con un Lean mas nuevo
# y no compila con v4.15.0. Si divergen, el REPL tampoco carga Mathlib.
WORKDIR /app/repl
RUN git clone --depth 1 --branch ${LEAN_VERSION} https://github.com/leanprover-community/repl.git . \
 && cp /app/mathproj/lean-toolchain . \
 && lake build

# El codigo Python se monta en runtime (-v "$PWD/src:/app/src"), no se hornea en la
# imagen: cambia a diario y reconstruir por eso costaria el cache de Mathlib.
WORKDIR /app
RUN pip3 install --break-system-packages --no-cache-dir jsonschema "langgraph>=0.2"

ENV PYTHONPATH=/app
ENV LEAN_PROJECT_DIR=/app/mathproj
ENV LEAN_REPL_BIN=/app/repl/.lake/build/bin/repl

CMD ["/bin/bash"]

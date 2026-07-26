FROM python:3.14-bookworm as base

# The following is adapted from:
# https://sourcery.ai/blog/python-docker/

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1

FROM node:24-bookworm-slim AS rmapi

# rmapi-js replaces the ddvk/rmapi Go binary. Installed from the GitHub release
# tarball: a packed tarball runs no lifecycle scripts, so this needs no bun, no
# devDependencies, no git and no typecheck. --ignore-scripts belts-and-braces.
#
# >=12.0.1 is required: 12.0.0 breaks every upload with "toHex is not a function".
ARG RMAPI_JS_VERSION=12.0.1
RUN npm install --prefix /opt/rmapi --ignore-scripts \
    "https://github.com/jwoglom/rmapi-js/releases/download/v${RMAPI_JS_VERSION}/jwoglom-rmapi-js-${RMAPI_JS_VERSION}.tgz"

FROM base AS python-deps

# Install pipenv and compilation dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc
RUN pip install pipenv

RUN mkdir -p /base
WORKDIR /base

# Install python dependencies in /.venv
COPY Pipfile .
COPY Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy
FROM base AS runtime

# Copy virtualenv from python-deps stage
COPY --from=python-deps /base/.venv /base/.venv
ENV PATH="/base/.venv/bin:$PATH"

# node needs libstdc++, which the non-slim bookworm base already provides
COPY --from=rmapi /usr/local/bin/node /usr/local/bin/node
COPY --from=rmapi /opt/rmapi /opt/rmapi
RUN ln -s /opt/rmapi/node_modules/.bin/rmapi-js /usr/local/bin/rmapi-js

# Fail the build rather than the job if the CLI can't actually start: a correct
# bin entry is not enough, the module graph has to resolve under Node's ESM
# resolver too.
RUN rmapi-js --version

ENV NO_COLOR=1

RUN playwright install-deps
RUN playwright install

# Create and switch to a new user
RUN useradd --create-home appuser
RUN mkdir -p /home/appuser/.cache/
RUN cp -r /root/.cache/ms-playwright /home/appuser/.cache/
RUN chown -R appuser /home/appuser/.cache

# rmapi-js needs this writable even when RMAPI_DEVICE_TOKEN is set: the session
# token and the hash cache are written here.
ENV RMAPI_CONFIG_DIR=/home/appuser/.config/rmapi-js
RUN mkdir -p "$RMAPI_CONFIG_DIR" && chown -R appuser /home/appuser/.config

WORKDIR /home/appuser
USER appuser

# Install application into container
COPY . .

# Run the application
ENTRYPOINT ["python3", "-u", "main.py"]